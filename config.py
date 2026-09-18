import os

from dotenv import load_dotenv

load_dotenv()


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

# --- WebRTC ---
STUN_SERVER = os.getenv("STUN_SERVER", "stun:stun.l.google.com:19302")
TURN_SERVER = os.getenv("TURN_SERVER", "turn:openrelay.metered.ca:80")
TURN_USERNAME = os.getenv("TURN_USERNAME", "openrelayproject")
TURN_PASSWORD = os.getenv("TURN_PASSWORD", "openrelayproject")

# --- Room lifecycle ---
ROOM_TIMEOUT_MINUTES = _int("ROOM_TIMEOUT_MINUTES", 30)
ROOM_GRACE_PERIOD_SECONDS = _int("ROOM_GRACE_PERIOD_SECONDS", 1800)
MAX_PEERS_PER_ROOM = _int("MAX_PEERS_PER_ROOM", 2)
ROOM_CLEANUP_INTERVAL_SECONDS = _int("ROOM_CLEANUP_INTERVAL_SECONDS", 60)

# --- Transfer limits ---
MAX_FILE_SIZE = _int("MAX_FILE_SIZE", 200 * 1024 * 1024)  # 200 MiB default
MAX_FILES = _int("MAX_FILES", 50)

# --- Auth ---
PASSWORD_MAX_ATTEMPTS = _int("PASSWORD_MAX_ATTEMPTS", 5)
PASSWORD_LOCKOUT_SECONDS = _int("PASSWORD_LOCKOUT_SECONDS", 300)

# --- Chunking ---
CHUNK_SIZE = _int("CHUNK_SIZE", 64 * 1024)  # 64 KiB

# --- Misc ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = _int("PORT", 8000)
DEBUG = _bool("DEBUG", False)