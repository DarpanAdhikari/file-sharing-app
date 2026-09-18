from flask import Blueprint, jsonify, request

from services.room_service import (
    InvalidPasswordError,
    InvalidRoomError,
    RoomError,
    RoomExpiredError,
    RoomFullError,
    RoomNotFoundError,
    room_service,
)

rooms_bp = Blueprint("rooms", __name__)


def _error(message, status=400):
    return jsonify({"error": message}), status


@rooms_bp.get("/rooms")
def list_rooms():
    rooms = room_service.list_public()
    return jsonify({"rooms": rooms})


@rooms_bp.post("/rooms")
def create_room():
    data = request.get_json(silent=True) or {}
    try:
        room = room_service.create_room(
            name=data.get("name"),
            password=data.get("password"),
            creator_name=data.get("displayName"),
            room_type=data.get("type"),
        )
    except InvalidRoomError as exc:
        return _error(str(exc))
    return jsonify({"room": room.public_metadata()}), 201


@rooms_bp.post("/rooms/<room_id>/authenticate")
def authenticate_room(room_id):
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    try:
        room = room_service.authenticate(room_id, password)
    except RoomNotFoundError:
        return _error("Room does not exist.", 404)
    except RoomExpiredError:
        return _error("Room has expired.", 410)
    except InvalidPasswordError as exc:
        return _error(str(exc), 403)
    return jsonify({"ok": True, "room": room.public_metadata()})