import pytest

from app import app, socketio
from services.room_service import room_service


@pytest.fixture(autouse=True)
def reset_rooms():
    room_service._rooms = {}
    room_service._failed_attempts = {}
    yield


def make_room(client):
    res = client.post(
        "/api/rooms",
        json={"name": "R", "password": "pw", "displayName": "Host", "type": "both"},
    )
    return res.get_json()["room"]


def authenticate(client, room_id, name, password="pw", is_creator=False):
    client.emit(
        "authenticate",
        {"roomId": room_id, "password": password, "displayName": name, "isCreator": is_creator},
    )
    received = client.get_received()
    for evt in received:
        if evt["name"] == "authenticated":
            return evt["args"][0]
    return None


def signal_events(client):
    return [e for e in client.get_received() if e["name"] == "signal"]


def test_signal_relay_with_null_target(client):
    room = make_room(client)

    host = socketio.test_client(app)
    host.emit("connect")
    host_info = authenticate(host, room["id"], "Host", is_creator=True)
    assert host_info is not None

    joiner = socketio.test_client(app)
    joiner.emit("connect")
    joiner_info = authenticate(joiner, room["id"], "Joiner")
    assert joiner_info is not None

    # The real client sends target: null for offers/answers.
    host.get_received()  # clear
    joiner.emit(
        "signal",
        {
            "roomId": room["id"],
            "target": None,
            "signal": {"sdp": {"type": "offer", "sdp": "v=0 test"}},
        },
    )

    host_signals = signal_events(host)
    assert len(host_signals) == 1
    payload = host_signals[0]["args"][0]
    assert payload["signal"]["sdp"]["type"] == "offer"
    assert payload["from"] == joiner_info["yourSid"]

    # Answer relays back to the joiner.
    joiner.get_received()
    host.emit(
        "signal",
        {
            "roomId": room["id"],
            "target": None,
            "signal": {"sdp": {"type": "answer", "sdp": "v=0 answer"}},
        },
    )
    joiner_signals = signal_events(joiner)
    assert len(joiner_signals) == 1
    assert joiner_signals[0]["args"][0]["signal"]["sdp"]["type"] == "answer"

    # Signals do not echo back to the sender.
    assert signal_events(joiner) == []
    assert signal_events(host) == []

    host.disconnect()
    joiner.disconnect()


def test_signal_relay_to_explicit_target(client):
    room = make_room(client)

    host = socketio.test_client(app)
    host.emit("connect")
    host_info = authenticate(host, room["id"], "Host", is_creator=True)

    joiner = socketio.test_client(app)
    joiner.emit("connect")
    joiner_info = authenticate(joiner, room["id"], "Joiner")

    host.get_received()
    joiner.emit(
        "signal",
        {
            "roomId": room["id"],
            "target": host_info["yourSid"],
            "signal": {"candidate": "c0 1 udp 1 1.2.3.4 1234 typ host", "sdpMid": "0"},
        },
    )
    host_signals = signal_events(host)
    assert len(host_signals) == 1
    assert host_signals[0]["args"][0]["signal"]["candidate"] == "c0 1 udp 1 1.2.3.4 1234 typ host"

    host.disconnect()
    joiner.disconnect()


def test_signal_ignored_when_not_in_room(client):
    room = make_room(client)
    outsider = socketio.test_client(app)
    outsider.emit("connect")
    outsider.emit(
        "signal",
        {"roomId": room["id"], "target": None, "signal": {"sdp": {"type": "offer"}}},
    )
    # No participant to receive it and no crash.
    assert signal_events(outsider) == []
    outsider.disconnect()