import time

from services.room_service import (
    InvalidPasswordError,
    InvalidRoomError,
    RoomExpiredError,
    RoomFullError,
    RoomNotFoundError,
    RoomService,
)


def make_service():
    svc = RoomService()
    svc._rooms = {}
    svc._failed_attempts = {}
    return svc


def test_create_room():
    svc = make_service()
    room = svc.create_room("Laptop", "secret", "Darpan", "send")
    assert room.name == "Laptop"
    assert room.id
    assert room.password_hash != "secret"


def test_create_room_invalid_name():
    svc = make_service()
    for bad in ("", "   ", "x" * 61):
        try:
            svc.create_room(bad, "pw", "N", "send")
            assert False, "should reject"
        except InvalidRoomError:
            pass


def test_create_room_requires_password():
    svc = make_service()
    try:
        svc.create_room("Room", "", "N", "send")
        assert False
    except InvalidRoomError:
        pass


def test_list_rooms_only_active():
    svc = make_service()
    svc.create_room("A", "pw", "N", "send")
    svc.create_room("B", "pw", "N", "send")
    rooms = svc.list_public()
    assert len(rooms) == 2
    assert all("password" not in r for r in rooms)
    assert all("id" in r for r in rooms)


def test_list_rooms_excludes_password_field():
    svc = make_service()
    room = svc.create_room("A", "super-secret", "N", "send")
    public = room.public_metadata()
    assert "password" not in public
    assert "passwordHash" not in public


def test_authenticate_correct_password():
    svc = make_service()
    room = svc.create_room("A", "pw123", "N", "send")
    result = svc.authenticate(room.id, "pw123")
    assert result.id == room.id


def test_authenticate_wrong_password():
    svc = make_service()
    room = svc.create_room("A", "pw123", "N", "send")
    try:
        svc.authenticate(room.id, "wrong")
        assert False
    except InvalidPasswordError:
        pass


def test_authenticate_unknown_room():
    svc = make_service()
    try:
        svc.authenticate("nope", "pw")
        assert False
    except RoomNotFoundError:
        pass


def test_room_full():
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    for i in range(room.max_peers):
        svc.add_peer(room, f"sid-{i}", f"peer{i}")
    try:
        svc.add_peer(room, "sid-extra", "extra")
        assert False
    except RoomFullError:
        pass


def test_remove_peer_reduces_count():
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    svc.add_peer(room, "s1", "p1")
    svc.add_peer(room, "s2", "p2")
    assert len(room.peers) == 2
    svc.remove_peer(room, "s1")
    assert len(room.peers) == 1


def test_find_room_for_sid():
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    svc.add_peer(room, "s1", "p1")
    rid, found = svc.find_room_for_sid("s1")
    assert rid == room.id
    assert found is room
    rid, found = svc.find_room_for_sid("ghost")
    assert rid is None
    assert found is None


def test_cleanup_expires_inactive_room(monkeypatch):
    import config
    monkeypatch.setattr(config, "ROOM_TIMEOUT_MINUTES", 0)
    monkeypatch.setattr(config, "ROOM_GRACE_PERIOD_SECONDS", -1)
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    svc.add_peer(room, "s1", "p1")
    removed = svc.cleanup()
    assert removed >= 1
    assert svc.get(room.id) is None


def test_cleanup_removes_orphan_room(monkeypatch):
    import config
    monkeypatch.setattr(config, "ROOM_GRACE_PERIOD_SECONDS", -1)
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    # no peers -> orphaned immediately
    removed = svc.cleanup()
    assert removed >= 1
    assert svc.get(room.id) is None


def test_expired_room_raises():
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    svc.expire_room(room.id)
    try:
        svc.get_active(room.id)
        assert False
    except RoomNotFoundError:
        pass


def test_rate_limit_password_attempts(monkeypatch):
    import config
    monkeypatch.setattr(config, "PASSWORD_MAX_ATTEMPTS", 3)
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    for _ in range(3):
        try:
            svc.authenticate(room.id, "wrong")
        except InvalidPasswordError:
            pass
    # now even a correct password should be blocked
    try:
        svc.authenticate(room.id, "pw")
        assert False
    except InvalidPasswordError:
        pass


def test_add_file_metadata():
    svc = make_service()
    room = svc.create_room("A", "pw", "N", "send")
    svc.add_file(room, {"name": "a.txt", "size": 10})
    assert len(room.files) == 1