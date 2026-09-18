from flask import Flask
from flask_socketio import SocketIO

import config
from routes.pages import pages_bp
from routes.rooms import rooms_bp

socketio = SocketIO(async_mode="threading")


def create_app():
    app = Flask(__name__)
    app.config.from_object("config")

    socketio.init_app(app)

    app.register_blueprint(pages_bp)
    app.register_blueprint(rooms_bp, url_prefix="/api")

    from services import signaling_service
    signaling_service.init_socketio(socketio)

    return app


app = create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        allow_unsafe_werkzeug=True,
    )