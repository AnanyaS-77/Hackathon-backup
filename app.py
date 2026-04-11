import os
import secrets
import tempfile
from datetime import timedelta

from flask import Flask

from db import init_app as init_db
from routes import bp as routes_bp


def load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path) as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def get_secret_key():
    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if secret_key:
        return secret_key

    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError("FLASK_SECRET_KEY must be set in production.")

    return secrets.token_hex(32)


def get_database_path(root_path):
    configured_path = os.environ.get("DATABASE_PATH")
    if configured_path:
        return configured_path

    if os.environ.get("VERCEL") == "1":
        return os.path.join(tempfile.gettempdir(), "arena.sqlite3")

    return os.path.join(root_path, "arena.sqlite3")


def create_app():
    load_env_file()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=get_secret_key(),
        DATABASE=get_database_path(app.root_path),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            os.environ.get("SESSION_COOKIE_SECURE") == "1"
            or os.environ.get("FLASK_ENV") == "production"
        ),
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_CONTENT_LENGTH", "65536")),
        PERMANENT_SESSION_LIFETIME=timedelta(
            minutes=int(os.environ.get("SESSION_TIMEOUT_MINUTES", "45"))
        ),
    )

    # Initialize the SQLite schema and legacy JSON migration before serving requests.
    init_db(app)
    app.register_blueprint(routes_bp)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
