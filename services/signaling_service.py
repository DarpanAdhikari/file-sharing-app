import threading
import time

from flask import request
from flask_socketio import emit, join_room as sio_join_room

import config
from services.room_service import (
    InvalidPasswordError,
    RoomError,
    RoomExpiredError,
    RoomFullError,
    RoomNotFoundError,
    room_service,
)

STUN = config.STUN_SERVER


def _ice_config():
    servers = [{"urls": STUN}]
    if config.TURN_SERVER:
        servers.append(
            {
                "urls": config.TURN_SERVER,
                "username": config.TURN_USERNAME,
                "credential": config.TURN_PASSWORD,
            }
        )
    return {"iceServers": servers}


def _emit_to_room(room_id, event, data, skip_sid=None):
    room = room_service.get(room_id)
    if room is None:
        return
    for sid in list(room.peers.keys()):
        if skip_sid and sid == skip_sid:
            continue
        emit(event, data, to=sid)


def _handle_create_room(data):
    try:
        room = room_service.create_room(
            name=data.get("name"),
            password=data.get("password"),
            creator_name=data.get("displayName"),
            room_type=data.get("type"),
        )
        room_service.add_peer(room, request.sid, data.get("displayName"), True)
        sio_join_room(room.id)
        emit("room_created", {"room": room.public_metadata()})
    except RoomError as exc:
        emit("error", {"error": str(exc)})


def _handle_authenticate(data):
    room_id = data.get("roomId")
    password = data.get("password") or ""
    display_name = (data.get("displayName") or "Guest").strip()[:40]
    try:
        room = room_service.authenticate(room_id, password)
    except RoomNotFoundError:
        emit("error", {"error": "Room does not exist."})
        return
    except RoomExpiredError:
        emit("error", {"error": "Room has expired."})
        return
    except InvalidPasswordError as exc:
        emit("auth_failed", {"error": str(exc)})
        return

    try:
        room_service.add_peer(room, request.sid, display_name)
    except RoomFullError:
        emit("error", {"error": "Room is full."})
        return

    sio_join_room(room.id)
    emit(
        "authenticated",
        {
            "room": room.public_metadata(),
            "iceConfig": _ice_config(),
            "yourSid": request.sid,
        },
    )
    _emit_to_room(room.id, "peer_joined", {"peer": request.sid}, skip_sid=request.sid)
    _emit_to_room(room.id, "room_updated", {"room": room.public_metadata()})


def _handle_signal(data):
    room_id = data.get("roomId")
    target = data.get("target")
    signal_type = data.get("type")

    room = room_service.get(room_id)
    if room is None or target is None:
        return
    if target not in room.peers:
        return
    if request.sid not in room.peers:
        return

    payload = {"from": request.sid, "signal": data.get("signal")}
    emit(signal_type, payload, to=target)


def _handle_heartbeat(data):
    room_id = data.get("roomId")
    if room_id:
        room_service.touch_peer(room_service.get(room_id), request.sid)


def _handle_room_join(data):
    # Intentionally thin: the socket "join room" concept is managed by the
    # signaling layer. Joining a room before auth is not allowed.
    room_id = data.get("roomId")
    room = room_service.get(room_id)
    if room is None or request.sid not in room.peers:
        emit("error", {"error": "Not authorized."})
        return
    sio_join_room(room_id)


def _handle_disconnect():
    room_id = None
    for rid, room in room_service._rooms.items():
        if request.sid in room.peers:
            room_id = rid
            break
    if room_id is None:
        return
    room = room_service.get(room_id)
    if room is None:
        return
    room_service.remove_peer(room, request.sid)
    _emit_to_room(room_id, "peer_left", {"peer": request.sid}, skip_sid=request.sid)
    _emit_to_room(room_id, "room_updated", {"room": room.public_metadata()})

    creator = room.creator_sid()
    if creator is None:
        # Creator gone; start grace countdown by expiring immediately.
        # Cleanup task also handles this if no peers remain.
        pass


def _cleanup_loop():
    while True:
        time.sleep(config.ROOM_CLEANUP_INTERVAL_SECONDS)
        room_service.cleanup()


def init_socketio(socketio):
    @socketio.on("create_room")
    def create_room(data):
        _handle_create_room(data or {})

    @socketio.on("authenticate")
    def authenticate(data):
        _handle_authenticate(data or {})

    @socketio.on("join")
    def join(data):
        _handle_room_join(data or {})

    @socketio.on("signal")
    def signal(data):
        _handle_signal(data or {})

    @socketio.on("heartbeat")
    def heartbeat(data):
        _handle_heartbeat(data or {})

    @socketio.on("disconnect")
    def disconnect():
        _handle_disconnect()

    thread = threading.Thread(target=_cleanup_loop, daemon=True)
    thread.start()