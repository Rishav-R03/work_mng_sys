import os

from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./worktracker.db")
    # Neon/Render hand out postgres:// or postgresql://; SQLAlchemy needs the driver name.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")
BASE_URL = (os.getenv("BASE_URL") or os.getenv("APP_BASE_URL") or "http://localhost:8000").strip().rstrip("/")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_SCOPE = os.getenv("GITHUB_SCOPE", "read:user repo")
# Comma-separated GitHub usernames allowed to sign in. Empty = anyone may sign in (each sees only their own data).
ALLOWED_GITHUB_LOGINS = {
    x.strip().lower() for x in os.getenv("ALLOWED_GITHUB_LOGIN", "").split(",") if x.strip()
}
DEV_LOGIN = os.getenv("DEV_LOGIN", "0") == "1"
HTTPS = BASE_URL.startswith("https://")
