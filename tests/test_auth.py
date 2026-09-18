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


def test_get_single_room_endpoint(client):
    room = client.post(
        "/api/rooms",
        json={"name": "A", "password": "pw", "displayName": "N", "type": "send"},
    ).get_json()["room"]
    res = client.get(f"/api/rooms/{room['id']}")
    assert res.status_code == 200
    body = res.get_json()["room"]
    assert body["name"] == "A"
    assert "password" not in body


def test_get_single_room_unknown(client):
    assert client.get("/api/rooms/nope").status_code == 404


def test_join_page_shows_room_name(client):
    room = client.post(
        "/api/rooms",
        json={"name": "Cool Room", "password": "pw", "displayName": "Alice", "type": "both"},
    ).get_json()["room"]
    res = client.get(f"/join/{room['id']}")
    assert res.status_code == 200
    assert b"Cool Room" in res.data


def test_join_page_inactive_room(client):
    res = client.get("/join/nonexistent")
    assert res.status_code == 200
    assert b"not active" in res.data


def test_create_room_validation(client):
    res = client.post("/api/rooms", json={"name": "", "password": "", "displayName": ""})
    assert res.status_code == 400


def test_join_page_serves(client):
    res = client.get("/join/abc123")
    assert res.status_code == 200


def test_room_page_redirects_dead_room_to_join(client):
    res = client.get("/room/abc123")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/join/abc123")