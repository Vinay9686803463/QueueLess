import os
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

# cspell:ignore dotenv Supabase
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False

# Load backend/.env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def get_database_url():
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from backend/.env")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql://", 1
        )

    parsed = urlparse(database_url)

    query_params = dict(parse_qsl(parsed.query))
    query_params.setdefault("sslmode", "require")

    # Use the installed psycopg2-binary driver
    if parsed.scheme == "postgresql":
        parsed = parsed._replace(scheme="postgresql+psycopg2")

    return urlunparse(
        parsed._replace(query=urlencode(query_params))
    )

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is missing from backend/.env")

    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in (
        "true", "1", "yes"
    )