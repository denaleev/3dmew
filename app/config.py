"""Settings come from environment variables (or the .env file next to the project)."""
import os
import secrets
import logging
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
log = logging.getLogger("kartochki")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class Settings:
    DATABASE_URL = _env("DATABASE_URL", "postgresql+psycopg://cards:cards@127.0.0.1:5432/cards")
    SECRET_KEY = _env("SECRET_KEY")
    PUBLIC_URL = _env("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    SESSION_DAYS = int(_env("SESSION_DAYS", "30"))
    MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "40"))

    ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
    CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5-5")
    AI_FILLS_PER_HOUR = int(_env("AI_FILLS_PER_HOUR", "60"))

    # who manages the shop: logins (lower-case) separated by commas, e.g. ADMIN_LOGINS=denis,anna
    ADMIN_LOGINS = {x.strip().lower() for x in _env("ADMIN_LOGINS").split(",") if x.strip()}
    # optional: a Telegram message to the admin about every new order and request
    TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
    # if api.telegram.org is not reachable from the server: a proxy, e.g. socks5://user:pass@host:1080 or http://host:3128
    TELEGRAM_PROXY = _env("TELEGRAM_PROXY")
    # new orders, requests and cancellations are also e-mailed to FEEDBACK_EMAIL (needs SMTP_*); 0 turns it off
    NOTIFY_EMAIL = _env("NOTIFY_EMAIL", "1") not in ("0", "no", "false", "")
    MAX_MODEL_MB = int(_env("MAX_MODEL_MB", "150"))  # one 3MF/STL file attached to a card
    MAX_REQUEST_FILES = int(_env("MAX_REQUEST_FILES", "10"))
    MAX_VIDEO_MB = int(_env("MAX_VIDEO_MB", "100"))  # one product video
    # feedback form: messages are saved in the admin panel and e-mailed through SMTP (Yandex: smtp.yandex.ru, 465)
    FEEDBACK_EMAIL = _env("FEEDBACK_EMAIL", "mew.shop@yandex.ru")
    SMTP_HOST = _env("SMTP_HOST", "smtp.yandex.ru")
    SMTP_PORT = int(_env("SMTP_PORT", "465"))
    SMTP_USER = _env("SMTP_USER")
    SMTP_PASSWORD = _env("SMTP_PASSWORD")
    # MAX messenger bot that posts products to a group (token from @MasterBot); the group is chosen in the admin panel
    MAX_BOT_TOKEN = _env("MAX_BOT_TOKEN")
    MAX_API = _env("MAX_API", "https://platform-api.max.ru")

    MODELS_DIR = Path(_env("MODELS_DIR", str(BASE_DIR / "models")))
    STATIC_DIR = Path(_env("STATIC_DIR", str(BASE_DIR / "static")))

    OAUTH = {
        "google": (_env("GOOGLE_CLIENT_ID"), _env("GOOGLE_CLIENT_SECRET")),
        "yandex": (_env("YANDEX_CLIENT_ID"), _env("YANDEX_CLIENT_SECRET")),
        "mailru": (_env("MAILRU_CLIENT_ID"), _env("MAILRU_CLIENT_SECRET")),
        "vk": (_env("VK_CLIENT_ID"), _env("VK_CLIENT_SECRET")),
    }

    @property
    def cookie_secure(self) -> bool:
        return self.PUBLIC_URL.startswith("https://")


settings = Settings()
if not settings.SECRET_KEY:
    settings.SECRET_KEY = secrets.token_urlsafe(48)
    log.warning("SECRET_KEY is not set: using a random one, sign-in links will break after a restart. Put SECRET_KEY into .env")
