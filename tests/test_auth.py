import pytest

from app import app


@pytest.fixture(autouse=True)
def reset_rooms():
    from services.room_service import room_service
    room_service._rooms = {}
    room_service._failed_attempts = {}
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_homepage_serves(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"P2P File Share" in res.data


def test_create_room_endpoint(client):
    res = client.post(
        "/api/rooms",
        json={"name": "Laptop", "password": "pw", "displayName": "Darpan", "type": "send"},
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["room"]["name"] == "Laptop"
    assert "password" not in body["room"]


def test_list_rooms_endpoint(client):
    client.post(
        "/api/rooms",
        json={"name": "A", "password": "pw", "displayName": "N", "type": "send"},
    )
    res = client.get("/api/rooms")
    assert res.status_code == 200
    assert len(res.get_json()["rooms"]) == 1


def test_authenticate_endpoint(client):
    room = client.post(
        "/api/rooms",
        json={"name": "A", "password": "pw", "displayName": "N", "type": "send"},
    ).get_json()["room"]
    ok = client.post(f"/api/rooms/{room['id']}/authenticate", json={"password": "pw"})
    assert ok.status_code == 200
    bad = client.post(f"/api/rooms/{room['id']}/authenticate", json={"password": "no"})
    assert bad.status_code == 403


def test_authenticate_unknown_room(client):
    res = client.post("/api/rooms/nope/authenticate", json={"password": "x"})
    assert res.status_code == 404


def test_create_room_validation(client):
    res = client.post("/api/rooms", json={"name": "", "password": "", "displayName": ""})
    assert res.status_code == 400


def test_join_page_serves(client):
    res = client.get("/join/abc123")
    assert res.status_code == 200


def test_room_page_serves(client):
    res = client.get("/room/abc123")
    assert res.status_code == 200
    assert b"Join QR code" in res.data or b"qr" in res.data