"""Accounts: name/e-mail + password, and sign-in through Google, Yandex, Mail.ru and VK ID."""
import base64
import hashlib
import logging
import re
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import OAuthAccount, User
from .security import (check_password, client_ip, current_user, current_user_optional, end_session, hash_password, is_admin,
                       new_id, rate_limit, sha256, sign, start_session, unsign)

router = APIRouter(prefix="/api")
log = logging.getLogger("kartochki.auth")

PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    "yandex": {
        "authorize": "https://oauth.yandex.ru/authorize",
        "token": "https://oauth.yandex.ru/token",
        "scope": "",
    },
    "mailru": {
        "authorize": "https://oauth.mail.ru/login",
        "token": "https://oauth.mail.ru/token",
        "scope": "userinfo",
    },
    "vk": {  # VK ID, OAuth 2.1 with PKCE
        "authorize": "https://id.vk.ru/authorize",
        "token": "https://id.vk.ru/oauth2/auth",
        "scope": "vkid.personal_info email",
    },
}


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "admin": is_admin(u)}


def enabled_providers() -> list[str]:
    return [p for p, (cid, sec) in settings.OAUTH.items() if cid and (sec or p == "vk")]


class Credentials(BaseModel):
    login: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=6, max_length=200)


def norm_login(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@router.get("/me")
def me(user: User | None = Depends(current_user_optional)):
    # 200 even for guests, so the browser console stays clean
    return user_out(user) if user else {"id": None}


@router.post("/auth/register")
def register(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit("reg:" + client_ip(request), 10, 3600)
    login = norm_login(data.login)
    if db.execute(select(User).where(User.login == login)).scalar_one_or_none():
        raise HTTPException(409, "Такое имя уже занято. Выбери другое или войди.")
    user = User(id=new_id(), login=login, name=re.sub(r"\s+", " ", data.login).strip()[:160], password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    start_session(db, response, user)
    return user_out(user)


@router.post("/auth/login")
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit("login:" + client_ip(request), 20, 600)
    user = db.execute(select(User).where(User.login == norm_login(data.login))).scalar_one_or_none()
    if not user or not check_password(user.password_hash, data.password):
        raise HTTPException(401, "Неверное имя или пароль")
    start_session(db, response, user)
    return user_out(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(db, request, response)
    response.status_code = 204
    return response


@router.get("/auth/providers")
def providers():
    return {"providers": enabled_providers()}


def redirect_uri(provider: str) -> str:
    return f"{settings.PUBLIC_URL}/api/auth/{provider}/callback"


def safe_next(path: str | None) -> str:
    """Only our own pages: /, /builder, /admin …"""
    return path if path and re.fullmatch(r"/[A-Za-z0-9_\-/]*", path) and not path.startswith("//") else "/"


@router.get("/auth/{provider}/start")
def oauth_start(provider: str, next: str = "/"):
    if provider not in enabled_providers():
        raise HTTPException(404, "Этот способ входа не настроен")
    cfg, (client_id, _) = PROVIDERS[provider], settings.OAUTH[provider]
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri(provider), "state": state}
    if cfg["scope"]:
        params["scope"] = cfg["scope"]
    if provider in ("google", "vk", "yandex"):
        params.update(code_challenge=challenge, code_challenge_method="S256")
    if provider == "google":
        params["prompt"] = "select_account"
    resp = RedirectResponse(cfg["authorize"] + "?" + urlencode(params), status_code=302)
    resp.set_cookie("oauth", sign({"p": provider, "s": state, "v": verifier, "n": safe_next(next)}), max_age=600, httponly=True,
                    secure=settings.cookie_secure, samesite="lax", path="/api/auth")
    return resp


def fetch_profile(provider: str, code: str, verifier: str, state: str, device_id: str | None) -> tuple[str, str]:
    """Exchange the code and return (provider user id, display name)."""
    cfg, (cid, secret) = PROVIDERS[provider], settings.OAUTH[provider]
    with httpx.Client(timeout=15) as http:
        if provider == "vk":
            form = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "client_id": cid,
                    "device_id": device_id or "", "redirect_uri": redirect_uri(provider), "state": state}
            tok = http.post(cfg["token"], data=form).raise_for_status().json()
            if "access_token" not in tok:
                raise ValueError(f"vk token: {tok.get('error')}")
            info = http.post("https://id.vk.ru/oauth2/user_info", data={"client_id": cid, "access_token": tok["access_token"]}).raise_for_status().json()
            u = info.get("user") or {}
            sub = str(u.get("user_id") or tok.get("user_id") or "")
            name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or "Пользователь VK"
            return sub, name
        form = {"grant_type": "authorization_code", "code": code, "client_id": cid, "client_secret": secret,
                "redirect_uri": redirect_uri(provider)}
        if provider in ("google", "yandex"):
            form["code_verifier"] = verifier
        tok = http.post(cfg["token"], data=form, headers={"Accept": "application/json"}).raise_for_status().json()
        at = tok["access_token"]
        if provider == "google":
            u = http.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {at}"}).raise_for_status().json()
            return str(u["sub"]), u.get("name") or u.get("email") or "Пользователь Google"
        if provider == "yandex":
            u = http.get("https://login.yandex.ru/info", params={"format": "json"}, headers={"Authorization": f"OAuth {at}"}).raise_for_status().json()
            return str(u["id"]), u.get("display_name") or u.get("real_name") or u.get("login") or "Пользователь Яндекса"
        u = http.get("https://oauth.mail.ru/userinfo", params={"access_token": at}).raise_for_status().json()
        return str(u["id"]), u.get("name") or u.get("email") or "Пользователь Mail.ru"


@router.get("/auth/{provider}/callback")
def oauth_callback(provider: str, request: Request, db: Session = Depends(get_db),
                   current: User | None = Depends(current_user_optional)):
    st = unsign(request.cookies.get("oauth"))
    q = request.query_params
    back = safe_next((st or {}).get("n"))
    fail = RedirectResponse(back + "?login=fail", status_code=302)
    if provider not in enabled_providers() or not st or st.get("p") != provider or q.get("state") != st.get("s") or not q.get("code"):
        return fail
    try:
        sub, name = fetch_profile(provider, q["code"], st["v"], st["s"], q.get("device_id"))
    except Exception as e:  # network/provider error: show a friendly message on the page
        log.warning("oauth %s failed: %s", provider, e)
        return fail
    if not sub:
        return fail
    sh = sha256(f"{provider}:{sub}")
    acc = db.execute(select(OAuthAccount).where(OAuthAccount.provider == provider, OAuthAccount.subject_hash == sh)).scalar_one_or_none()
    if acc:
        user = db.get(User, acc.user_id)
    else:
        user = current or User(id=new_id(), login=None, name=name[:160])
        if not current:
            db.add(user)
            db.flush()
        db.add(OAuthAccount(user_id=user.id, provider=provider, subject_hash=sh))
        db.commit()
    resp = RedirectResponse(back + "?login=ok", status_code=302)
    resp.delete_cookie("oauth", path="/api/auth")
    start_session(db, resp, user)
    return resp
