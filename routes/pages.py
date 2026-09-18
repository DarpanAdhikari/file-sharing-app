import base64
import io

import qrcode
from flask import Blueprint, render_template, url_for

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
    return render_template("join.html", room_id=room_id)


@pages_bp.get("/room/<room_id>")
def room(room_id):
    return render_template("room.html", room_id=room_id, qr=_room_qr_data_uri(room_id))