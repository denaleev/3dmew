import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import LoginSession, User

COOKIE = "sid"
_ph = PasswordHasher()  # argon2id with safe defaults


def new_id() -> str:
    return uuid.uuid4().hex


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def check_password(stored: str | None, pw: str) -> bool:
    if not stored:
        return False
    try:
        return _ph.verify(stored, pw)
    except (VerificationError, InvalidHashError):
        return False


def start_session(db: Session, resp: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=sha256(token), user_id=user.id,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.SESSION_DAYS)))
    db.execute(delete(LoginSession).where(LoginSession.expires_at < datetime.now(timezone.utc)))
    db.commit()
    resp.set_cookie(COOKIE, token, max_age=settings.SESSION_DAYS * 86400, httponly=True,
                    secure=settings.cookie_secure, samesite="lax", path="/")


def end_session(db: Session, request: Request, resp: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == sha256(token)))
        db.commit()
    resp.delete_cookie(COOKIE, path="/")


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.execute(select(LoginSession).where(LoginSession.token_hash == sha256(token))).scalar_one_or_none()
    if not row or row.expires_at < datetime.now(timezone.utc):
        return None
    return db.get(User, row.user_id)


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if not user:
        raise HTTPException(401, "Нужно войти в аккаунт")
    return user


def is_admin(user: User | None) -> bool:
    return bool(user and (user.is_admin or (user.login and user.login in settings.ADMIN_LOGINS)))


def current_admin(user: User = Depends(current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(403, "Только для администратора магазина")
    return user


# --- signed short-lived cookie for the OAuth round trip (state + PKCE verifier) ---
def sign(data: dict, ttl: int = 600) -> str:
    raw = json.dumps({**data, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    mac = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + mac


def unsign(value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    good = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    return data if data.get("exp", 0) >= time.time() else None


# --- tiny in-memory rate limiter (per process) ---
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(key: str, limit: int, window: int) -> None:
    now = time.time()
    q = _hits[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Слишком много попыток, подожди немного")
    q.append(now)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    # nginx appends the real address at the end ($proxy_add_x_forwarded_for); the first ones can be forged
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "?")
