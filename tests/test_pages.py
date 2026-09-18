import pytest

from services.room_service import room_service


def _create(client, name="Laptop", password="pw", display="Darpan"):
    resp = client.post(
        "/api/rooms",
        json={"name": name, "password": password, "displayName": display, "type": "both"},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["room"]


def test_join_page_shows_fresh_room(client):
    room = _create(client)
    resp = client.get(f"/join/{room['id']}")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "Room: <strong>Laptop</strong>" in text
    assert "window.ROOM_EXISTS = true" in text
    assert "Create a new room" not in text


def test_join_page_inactive_room_offers_create(client):
    resp = client.get("/join/000000000000000000")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "window.ROOM_EXISTS = false" in text
    assert "Create a new room" in text


def test_room_page_renders_when_active(client):
    room = _create(client)
    resp = client.get(f"/room/{room['id']}")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert room["id"] in text
    assert "copy-invite-btn" in text


def test_room_page_redirects_when_missing(client):
    resp = client.get("/room/000000000000000000")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/join/000000000000000000")


def test_room_page_redirects_when_expired(client):
    room = _create(client)
    room_service.expire_room(room["id"])
    resp = client.get(f"/room/{room['id']}")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/join/{room['id']}")