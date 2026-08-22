import os


class Config:
    # --- Core ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # --- Database ---
    _raw_db_url = os.environ.get("DATABASE_URL", "")
    if _raw_db_url.startswith("postgres://"):
        # Render / Heroku style URLs use the old "postgres://" scheme,
        # SQLAlchemy 2.x requires "postgresql://"
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url or "postgresql://localhost/eyewear"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Google Identity ---
    GOOGLE_CLIENT_ID = os.environ.get(
        "GOOGLE_CLIENT_ID",
        "1053775974665-gmkcbkch8h81joinmk9l5o9ep75mr1pe.apps.googleusercontent.com",
    )
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # --- Store ---
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "smartmind2910@gmail.com")
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "919718709078")

    # --- Uploads ---
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "frontend", "static", "uploads")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB per request
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

    # --- Sessions / cookies ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
