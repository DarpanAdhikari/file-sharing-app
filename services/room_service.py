import secrets
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

import config

ROOM_TYPES = ("send", "receive", "both")
ROOM_STATUS = ("active", "waiting", "expired")


class RoomError(Exception):
    pass


class RoomNotFoundError(RoomError):
    pass


class RoomExpiredError(RoomError):
    pass


class RoomFullError(RoomError):
    pass


class InvalidPasswordError(RoomError):
    pass


class InvalidRoomError(RoomError):
    pass


class Peer:
    def __init__(self, sid, display_name, is_creator=False):
        self.sid = sid
        self.display_name = display_name
        self.is_creator = is_creator
        self.authenticated = False
        self.joined_at = time.time()
        self.last_seen = time.time()

    def touch(self):
        self.last_seen = time.time()

    def to_public(self):
        return {
            "name": self.display_name,
            "isCreator": self.is_creator,
        }


class Room:
    def __init__(self, room_id, name, password, creator_name, room_type):
        self.id = room_id
        self.name = name
        self.password_hash = generate_password_hash(password)
        self.creator_name = creator_name
        self.room_type = room_type
        self.max_peers = config.MAX_PEERS_PER_ROOM
        self.created_at = time.time()
        self.last_activity = time.time()
        self.peers = {}  # sid -> Peer
        self.files = []  # metadata only
        self.expired = False

    def touch(self):
        self.last_activity = time.time()

    def creator_sid(self):
        for sid, peer in self.peers.items():
            if peer.is_creator:
                return sid
        return None

    def public_metadata(self):
        return {
            "id": self.id,
            "name": self.name,
            "creator": self.creator_name,
            "type": self.room_type,
            "passwordProtected": True,
            "peerCount": len(self.peers),
            "maxPeers": self.max_peers,
            "fileCount": len(self.files),
            "peers": [p.to_public() for p in self.peers.values()],
            "createdAt": self.created_at,
            "lastActivity": self.last_activity,
            "expired": self.expired,
        }


class RoomService:
    def __init__(self):
        self._rooms = {}
        self._lock = threading.RLock()
        self._failed_attempts = {}  # room_id -> list of timestamps

    def create_room(self, name, password, creator_name, room_type):
        name = (name or "").strip()
        creator_name = (creator_name or "").strip()
        room_type = (room_type or "both").strip().lower()

        if not name or len(name) > 60:
            raise InvalidRoomError("Room name must be 1-60 characters.")
        if not creator_name or len(creator_name) > 40:
            raise InvalidRoomError("Display name must be 1-40 characters.")
        if not password:
            raise InvalidRoomError("A password is required.")
        if len(password) > 200:
            raise InvalidRoomError("Password is too long.")
        if room_type not in ROOM_TYPES:
            raise InvalidRoomError("Invalid room type.")

        room_id = self._generate_id()
        with self._lock:
            room = Room(room_id, name, password, creator_name, room_type)
            self._rooms[room_id] = room
        return room

    def _generate_id(self):
        while True:
            candidate = secrets.token_hex(4)
            if candidate not in self._rooms:
                return candidate

    def get(self, room_id):
        return self._rooms.get(room_id)

    def get_active(self, room_id):
        room = self.get(room_id)
        if room is None:
            raise RoomNotFoundError("Room does not exist.")
        if room.expired:
            raise RoomExpiredError("Room has expired.")
        return room

    def list_public(self):
        with self._lock:
            rooms = [
                room.public_metadata()
                for room in self._rooms.values()
                if not room.expired
            ]
        rooms.sort(key=lambda r: r["lastActivity"], reverse=True)
        return rooms

    def authenticate(self, room_id, password):
        room = self.get_active(room_id)
        if self._is_rate_limited(room_id):
            raise InvalidPasswordError("Too many attempts. Try again later.")
        if not check_password_hash(room.password_hash, password):
            self._register_attempt(room_id)
            raise InvalidPasswordError("Incorrect password.")
        self._clear_attempts(room_id)
        return room

    def _register_attempt(self, room_id):
        now = time.time()
        with self._lock:
            attempts = self._failed_attempts.setdefault(room_id, [])
            attempts.append(now)
            attempts[:] = [
                t for t in attempts
                if now - t < config.PASSWORD_LOCKOUT_SECONDS
            ]

    def _is_rate_limited(self, room_id):
        with self._lock:
            attempts = self._failed_attempts.get(room_id, [])
            now = time.time()
            attempts[:] = [
                t for t in attempts
                if now - t < config.PASSWORD_LOCKOUT_SECONDS
            ]
            return len(attempts) >= config.PASSWORD_MAX_ATTEMPTS

    def _clear_attempts(self, room_id):
        with self._lock:
            self._failed_attempts.pop(room_id, None)

    def add_peer(self, room, sid, display_name, is_creator=False):
        with self._lock:
            if sid in room.peers:
                return
            if len(room.peers) >= room.max_peers and not is_creator:
                raise RoomFullError("Room is full.")
            room.peers[sid] = Peer(sid, display_name, is_creator)
            room.touch()

    def remove_peer(self, room, sid):
        with self._lock:
            if sid in room.peers:
                del room.peers[sid]
                room.touch()

    def add_file(self, room, metadata):
        with self._lock:
            if len(room.files) >= config.MAX_FILES:
                raise RoomError("Maximum file count reached.")
            room.files.append(metadata)
            room.touch()

    def touch_peer(self, room, sid):
        peer = room.peers.get(sid)
        if peer:
            peer.touch()
            room.touch()

    def expire_room(self, room_id):
        with self._lock:
            room = self._rooms.get(room_id)
            if room:
                room.expired = True
                del self._rooms[room_id]

    def cleanup(self):
        """Remove expired rooms based on inactivity and grace periods."""
        now = time.time()
        timeout = config.ROOM_TIMEOUT_MINUTES * 60
        grace = config.ROOM_GRACE_PERIOD_SECONDS
        to_expire = []
        with self._lock:
            for room_id, room in self._rooms.items():
                active_peers = room.peers
                if active_peers:
                    inactive = now - room.last_activity > timeout
                    if inactive:
                        to_expire.append(room_id)
                else:
                    orphaned = now - room.last_activity > grace
                    if orphaned:
                        to_expire.append(room_id)
        for room_id in to_expire:
            self.expire_room(room_id)
        return len(to_expire)


room_service = RoomService()