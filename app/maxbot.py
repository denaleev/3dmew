"""Posting products to a MAX messenger group through a bot (button «📣 В MAX» on the shop page, admins only)."""
import html
import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Product, ShopSetting, User
from .security import current_admin
from .shop import get_setting

log = logging.getLogger("kartochki.max")
router = APIRouter(prefix="/api/admin/max")


def headers() -> dict:
    if not settings.MAX_BOT_TOKEN:
        raise HTTPException(400, "Бот MAX не подключён: впиши MAX_BOT_TOKEN в .env и перезапусти сайт")
    return {"Authorization": settings.MAX_BOT_TOKEN}


def call(method: str, path: str, **kw) -> dict:
    try:
        r = httpx.request(method, settings.MAX_API + path, headers=headers(), timeout=30, **kw)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"MAX не отвечает: {e}")
    if r.status_code >= 400:
        try:
            j = r.json()
            msg = j.get("message") or j.get("error") or r.text
        except ValueError:
            msg = r.text
        raise HTTPException(502, f"MAX: {msg[:300]}")
    return r.json() if r.content else {}


def upload_image(data: bytes) -> dict:
    """Returns the payload of an image attachment."""
    up = call("POST", "/uploads", params={"type": "image"})
    url = up.get("url")
    if not url:
        raise HTTPException(502, "MAX не дал адрес для загрузки картинки")
    try:
        r = httpx.post(url, files={"data": ("card.jpg", data, "image/jpeg")}, headers=headers(), timeout=60)
        r.raise_for_status()
        j = r.json() if r.content else {}
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(502, f"MAX: картинка не загрузилась ({e})")
    if j.get("token"):
        return {"token": j["token"]}
    if j.get("photos"):
        return {"photos": j["photos"]}
    if up.get("token"):
        return {"token": up["token"]}
    raise HTTPException(502, "MAX не вернул токен картинки")


def caption(p: Product, shop: dict) -> str:
    lines = [f"<b>{html.escape(p.title)}</b>", f"💰 {p.price:.0f} ₽" + (f" <s>{p.old_price:.0f} ₽</s>" if p.old_price else "")]
    lines.append("✅ В наличии" + (f": {p.stock} шт." if p.stock else "") if (p.stock or 0) > 0 else "🖨 Печатаем под заказ")
    if p.description:
        lines += ["", html.escape(p.description[:700])]
    feats = [ln.strip() for ln in (p.features or "").splitlines() if ln.strip()][:6]
    if feats:
        lines += [""] + [f"• {html.escape(x)}" for x in feats]
    if shop.get("name"):
        lines += ["", html.escape(shop["name"])]
    return "\n".join(lines)[:3900]


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    cfg = get_setting(db, "max_bot")
    out = {"configured": bool(settings.MAX_BOT_TOKEN), "chat_id": cfg.get("chat_id"), "chat_title": cfg.get("chat_title", "")}
    if settings.MAX_BOT_TOKEN:
        try:
            me = call("GET", "/me")
            out["bot"] = me.get("name") or me.get("username") or ""
            chats = call("GET", "/chats", params={"count": 100}).get("chats") or []
            out["chats"] = [{"chat_id": c.get("chat_id"), "title": c.get("title") or str(c.get("chat_id")),
                             "type": c.get("type")} for c in chats if c.get("type") in ("chat", "channel")]
        except HTTPException as e:
            out["error"] = e.detail
    return out


class ChatIn(BaseModel):
    chat_id: int
    chat_title: str = ""


@router.put("/chat")
def set_chat(data: ChatIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    row = db.get(ShopSetting, "max_bot") or ShopSetting(key="max_bot", data={})
    row.data = {"chat_id": data.chat_id, "chat_title": data.chat_title[:200]}
    db.add(row)
    db.commit()
    return {"ok": True}


@router.post("/post/{pid}")
def post_product(pid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    from .shop import shop_info

    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Товар не найден")
    chat = get_setting(db, "max_bot").get("chat_id")
    if not chat:
        raise HTTPException(400, "Выбери группу для бота MAX: Админка → Настройки → Бот MAX")
    shop = shop_info(db)
    atts = []
    if p.image:
        atts.append({"type": "image", "payload": upload_image(p.image)})
    if settings.PUBLIC_URL.startswith("https://"):
        atts.append({"type": "inline_keyboard", "payload": {"buttons": [[
            {"type": "link", "text": "🛒 Открыть в магазине", "url": f"{settings.PUBLIC_URL}/p/{p.id}"}]]}})
    body = {"text": caption(p, shop), "format": "html", "attachments": atts}
    for wait in (0.5, 1, 2, 4, 8):  # MAX needs a moment to process an uploaded picture
        time.sleep(wait)
        try:
            call("POST", "/messages", params={"chat_id": chat}, json=body)
            return {"ok": True}
        except HTTPException as e:
            if "not.processed" not in str(e.detail) and "not.ready" not in str(e.detail):
                raise
            log.info("max: attachment not ready, retrying")
    raise HTTPException(502, "MAX долго обрабатывает картинку, попробуй ещё раз через минуту")
