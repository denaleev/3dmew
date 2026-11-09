"""Personal account of a buyer: profile (contacts for the next orders), password, sign-in methods, deleting the account."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import CustomRequest, Favorite, LoginSession, OAuthAccount, Order, Review, User
from .security import (COOKIE, check_password, client_ip, current_user, end_session, hash_password, is_admin,
                       rate_limit, sha256)
from .shop import DELIVERY, clean

router = APIRouter(prefix="/api/account")
PROVIDER_NAMES = {"google": "Google", "yandex": "Яндекс", "mailru": "Mail.ru", "vk": "VK ID"}


def account_out(db: Session, u: User) -> dict:
    count = lambda m: db.execute(select(func.count()).select_from(m).where(m.user_id == u.id)).scalar_one()
    providers = sorted(set(db.execute(select(OAuthAccount.provider).where(OAuthAccount.user_id == u.id)).scalars()))
    return {"id": u.id, "name": u.name, "login": u.login if u.password_hash else None, "admin": is_admin(u),
            "phone": u.phone or "", "email": u.email or "", "address": u.address or "", "delivery": u.delivery or "",
            "has_password": bool(u.password_hash), "providers": [{"id": p, "name": PROVIDER_NAMES.get(p, p)} for p in providers],
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "counts": {"orders": count(Order), "requests": count(CustomRequest), "favorites": count(Favorite),
                       "reviews": count(Review)}}


@router.get("")
def get_account(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return account_out(db, user)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=1000)
    delivery: str | None = Field(default=None, max_length=40)


@router.patch("")
def save_profile(data: ProfileIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.name is not None:
        name = clean(data.name, 160)
        if not name:
            raise HTTPException(400, "Имя не может быть пустым")
        user.name = name
    if data.email is not None:
        e = clean(data.email, 160)
        if e and ("@" not in e or " " in e):
            raise HTTPException(400, "Проверь адрес почты")
        user.email = e
    if data.phone is not None:
        user.phone = clean(data.phone, 60)
    if data.address is not None:
        user.address = clean(data.address, 1000)
    if data.delivery is not None:
        user.delivery = data.delivery if data.delivery in DELIVERY else ""
    db.commit()
    return account_out(db, user)


class PasswordIn(BaseModel):
    old: str = Field(default="", max_length=200)
    new: str = Field(min_length=6, max_length=200)


@router.post("/password")
def change_password(data: PasswordIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rate_limit("pw:" + client_ip(request), 10, 600)
    if user.password_hash and not check_password(user.password_hash, data.old):
        raise HTTPException(400, "Текущий пароль указан неверно")
    user.password_hash = hash_password(data.new)
    # sign out everywhere else: other devices keep no access with the old password
    token = request.cookies.get(COOKIE) or ""
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id, LoginSession.token_hash != sha256(token)))
    db.commit()
    return {"ok": True}


@router.post("/logout-all")
def logout_everywhere(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
    end_session(db, request, response)
    return {"ok": True}


class DeleteIn(BaseModel):
    confirm: str = Field(max_length=40)
    password: str = Field(default="", max_length=200)


@router.post("/delete")
def delete_account(data: DeleteIn, request: Request, response: Response, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """Deletes the account and the personal data in it. Orders stay for the shop's accounting, without the link to the account."""
    if is_admin(user):
        raise HTTPException(400, "Аккаунт администратора удалить отсюда нельзя")
    if data.confirm.strip().lower() != "удалить":
        raise HTTPException(400, "Чтобы подтвердить, впиши слово «удалить»")
    if user.password_hash and not check_password(user.password_hash, data.password):
        raise HTTPException(400, "Пароль указан неверно")
    end_session(db, request, response)
    db.delete(user)
    db.commit()
    return {"ok": True}
