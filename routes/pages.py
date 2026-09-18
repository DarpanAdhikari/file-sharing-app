import base64
import io

import qrcode
from flask import Blueprint, redirect, render_template, url_for

import config
from services.room_service import room_service

pages_bp = Blueprint("pages", __name__)


def _room_qr_data_uri(room_id):
    join_url = url_for("pages.join", room_id=room_id, _external=True)
    img = qrcode.make(join_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{data}"


@pages_bp.get("/")
def index():
    return render_template("index.html")


@pages_bp.get("/join/<room_id>")
def join(room_id):
    room = room_service.resolve(room_id)
    room = None if (room is None or room.expired) else room
    room_meta = room.public_metadata() if room else None
    return render_template(
        "join.html",
        room_id=room_id,
        room_name=room_meta["name"] if room_meta else None,
        room_creator=room_meta["creator"] if room_meta else None,
        room_type=room_meta["type"] if room_meta else None,
        room_exists=room_meta is not None,
    )


@pages_bp.get("/room/<room_id>")
def room(room_id):
    room = room_service.resolve(room_id)
    if room is None or room.expired:
        return redirect(url_for("pages.join", room_id=room_id))
    return render_template(
        "room.html",
        room_id=room_id,
        qr=_room_qr_data_uri(room_id),
        max_file_size=config.MAX_FILE_SIZE,
    )