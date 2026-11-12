"""The shop for customers: catalogue of published cards, orders, custom print requests with files."""
import hmac
import io
import logging
import re
import secrets
import threading
from decimal import Decimal
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import pricing
from .config import settings
from .db import get_db
from .models import (Category, CustomRequest, FilamentColor, Order, OrderEvent, OrderItem, Product, ProductMedia, RequestFile,
                     ShopSetting, User)
from .security import client_ip, current_user, current_user_optional, is_admin, rate_limit

router = APIRouter(prefix="/api/shop")
log = logging.getLogger("kartochki.shop")

ORDER_LABELS = {"new": "Новый", "confirmed": "Подтверждён", "printing": "Печатается", "ready": "Готов",
                "shipped": "Отправлен", "done": "Выполнен", "cancelled": "Отменён"}
REQUEST_LABELS = {"new": "Новая", "reviewing": "Смотрим", "quoted": "Есть цена", "accepted": "Согласована",
                  "rejected": "Отклонена", "ordered": "Оформлен заказ"}
DELIVERY = {"pickup": "Самовывоз", "courier": "Курьер по городу", "post": "Почта России", "cdek": "СДЭК"}
FOOTER_DEFAULT = ("© 2026 3D-мастерская — творческий проект юного автора при поддержке родителей. Представленные работы "
                  "являются примерами изделий, созданных методом 3D-печати. Возможность приобретения уточняется "
                  "индивидуально. Все вопросы, связанные с приобретением изделий, решаются при участии родителей. "
                  "Для консультации используйте форму обратной связи.")
ABOUT_DEFAULT = """Привет! Это мой творческий проект, в котором я учусь 3D-моделированию, печати и созданию интересных вещей.
Здесь я делюсь своими работами, экспериментирую с дизайном и пробую воплощать новые идеи.

✨ Важная информация:
- Проект носит творческий и экспериментальный характер.
- Изделия создаются небольшими партиями или индивидуально, с учётом технических возможностей 3D-печати.
- Фотографии представлены для ознакомления с примерами работ. Цвет, текстура и отдельные детали готового изделия могут немного отличаться.
- Размеры, материалы, цвета и назначение изделий уточняются в описании конкретной работы.
- Возможность приобретения отдельных готовых изделий обсуждается индивидуально со взрослыми организаторами проекта.
- Все вопросы, связанные с приобретением изделий, оплатой и передачей, решаются при участии родителей.
- Изделия предназначены для декоративного или бытового использования, если в описании конкретной модели не указано иное.
- Если с изделием возникла проблема, пожалуйста, свяжитесь со мной — мы постараемся её решить.

📩 По вопросам и предложениям пишите через форму обратной связи.

Спасибо, что поддерживаете мой творческий эксперимент! 🚀"""
SHOP_DEFAULTS = {"name": "3DМяу", "tagline": "Милые вещи, напечатанные на 3D-принтере, и печать ваших идей на заказ",
                 "phone": "", "email": "", "telegram": "", "max": "", "max_link": "", "vk": "", "address": "", "delivery": list(DELIVERY),
                 "min_order": 0, "about": ABOUT_DEFAULT, **{k: "" for k in ("page_terms", "page_privacy", "page_consent", "page_seller")},
                 # seller details (shown in the footer and on the legal pages; must be an adult seller)
                 "seller_name": "", "seller_status": "самозанятый (плательщик НПД)", "seller_inn": "",
                 "seller_ogrnip": "", "city": "", "make_days": "3–7 дней",
                 "pay_text": "", "delivery_text": "", "returns_text": "",
                 "age_note": "Изделия могут содержать мелкие детали и не предназначены для детей до 3 лет. "
                             "Не для контакта с пищевыми продуктами, если в описании не сказано иное.",
                 "policy_date": "09.11.2026",
                 "footer_text": FOOTER_DEFAULT, "meta_description": ("Котики, антистрессы, декор и подарки, напечатанные на 3D-принтере. Готовые изделия и печать "
                                     "по вашей идее, выбор цвета пластика."), "about_title": "Моя маленькая 3D-мастерская"}
LONG_TEXT = {"pay_text", "delivery_text", "returns_text", "age_note", "about", "footer_text"}
PAGE_TEXT = {"page_terms", "page_privacy", "page_consent", "page_seller"}  # footer pages rewritten by the admin (empty = standard text)
CONSENT_TEXT = "Согласие на обработку персональных данных и согласие с условиями заказа получены"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp", ".stl", ".3mf", ".obj", ".step", ".stp",
               ".pdf", ".zip", ".txt"}


# ---------------------------------------------------------------- helpers ----

def f(x) -> float | None:
    return float(x) if isinstance(x, Decimal) else x


def get_setting(db: Session, key: str) -> dict:
    row = db.get(ShopSetting, key)
    return dict(row.data) if row and row.data else {}


def shop_info(db: Session) -> dict:
    s = {**SHOP_DEFAULTS, **get_setting(db, "shop")}
    for k in ("about", "about_title"):  # older installs saved these keys empty
        if not str(s.get(k) or "").strip():
            s[k] = SHOP_DEFAULTS[k]
    return s


def calc_settings(db: Session) -> dict:
    return pricing.merge_settings(get_setting(db, "calc"))


def who(user: User | None, fallback: str) -> str:
    return user.name if user else fallback


def add_event(db: Session, *, order_id=None, request_id=None, who_: str, status=None, text="") -> None:
    db.add(OrderEvent(order_id=order_id, request_id=request_id, who=who_[:160], status=status, text=text[:4000]))


def tg_send(text: str, timeout: float = 10) -> httpx.Response:
    with httpx.Client(proxy=settings.TELEGRAM_PROXY or None, timeout=timeout) as c:
        return c.post(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text[:4000]})


def notify(text: str, mail: bool = True) -> None:
    """A message to the admin: to Telegram and by e-mail. Never blocks or breaks the request."""
    tg = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)
    em = mail and settings.NOTIFY_EMAIL and bool(settings.SMTP_USER and settings.SMTP_PASSWORD)
    if not (tg or em):
        return

    def send():
        if em:  # first the mail: Telegram may hang if it is blocked at the hosting
            from .catalog import send_mail
            if not send_mail(text.splitlines()[0][:150], text):
                log.warning("notify e-mail was not sent")
        if tg:
            try:
                r = tg_send(text)
                if r.status_code != 200:
                    log.warning("telegram: %s %s", r.status_code, r.text[:300])
            except Exception as e:  # noqa: BLE001
                log.warning("telegram: %s", e)
    threading.Thread(target=send, daemon=True).start()


def jpeg(data: bytes, max_side: int, quality: int = 86) -> bytes:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def tile_from_card(data: bytes, layout: str = "") -> bytes | None:
    """Catalogue preview of a ready card made in the builder's main layout: the price plate at the bottom is cut off
    and the background just above it is stretched down, so the picture keeps its 3:4 shape."""
    if layout not in ("", "info"):
        return None
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    w, h = img.size
    if h / w < 1.2:
        return None
    cut = int(h - (64 + 178 + 18) * w / 1200)
    top = img.crop((0, 0, w, cut))
    strip = img.crop((0, cut - 12, w, cut)).resize((w, h - cut), Image.BICUBIC)
    out = Image.new("RGB", (w, h))
    out.paste(top, (0, 0))
    out.paste(strip, (0, cut))
    b = io.BytesIO()
    out.save(b, "JPEG", quality=88)
    return jpeg(b.getvalue(), 520, 84)


def stamp(dt) -> int:
    return int(dt.timestamp()) if dt else 0


def product_out(p: Product, full: bool = False, sold: int | None = None) -> dict:
    o = {"id": p.id, "title": p.title, "price": f(p.price), "old_price": f(p.old_price), "category": p.category,
         "material": p.material, "stock": p.stock, "print_minutes": p.print_minutes, "published": p.published,
         "colors": list(p.colors or []),
         "thumb": f"/api/shop/products/{p.id}/thumb?v={stamp(p.updated_at)}",
         "tile": f"/api/shop/products/{p.id}/{'tile' if p.tile else 'thumb'}?v={stamp(p.updated_at)}",
         "image": f"/api/shop/products/{p.id}/image?v={stamp(p.updated_at)}"}
    if sold is not None:
        o["sold"] = sold
    if full:
        o.update(description=p.description, note=p.note or "", features=[
            {"k": a.strip(), "v": b.strip()} for a, _, b in (ln.partition(":") for ln in p.features.splitlines()) if a.strip()
        ])
    return o


def order_out(o: Order, items: list[OrderItem], events: list[OrderEvent] | None = None, admin: bool = False) -> dict:
    d = {"id": o.id, "status": o.status, "status_label": ORDER_LABELS.get(o.status, o.status),
         "name": o.name, "phone": o.phone, "email": o.email, "delivery": o.delivery,
         "delivery_label": DELIVERY.get(o.delivery, o.delivery), "address": o.address, "comment": o.comment,
         "total": f(o.total), "paid": o.paid, "request_id": o.request_id,
         "due_date": o.due_date.date().isoformat() if o.due_date else None,
         "created_at": o.created_at.isoformat() if o.created_at else None,
         "updated_at": o.updated_at.isoformat() if o.updated_at else None,
         "items": [{"id": i.id, "product_id": i.product_id, "title": i.title, "price": f(i.price), "qty": i.qty,
                    "note": i.note, "color": i.color or "", "price_pending": bool(i.price_pending), **({"cost": f(i.cost), "print_minutes": i.print_minutes, "grams": f(i.grams),
                                        "from_stock": i.from_stock} if admin else {})} for i in items]}
    d["price_pending"] = any(i.price_pending for i in items)
    if admin:
        d.update(token=o.token, user_id=o.user_id, admin_note=o.admin_note, cost=f(o.cost), source=o.source or "",
                 print_minutes=o.print_minutes, grams=f(o.grams),
                 closed_at=o.closed_at.isoformat() if o.closed_at else None)
    if events is not None:
        d["events"] = [{"at": e.at.isoformat(), "who": e.who if admin else ("магазин" if e.who != o.name else e.who),
                        "status": e.status, "status_label": ORDER_LABELS.get(e.status or "", ""), "text": e.text}
                       for e in events if admin or e.status or not e.text.startswith("🔒")]
    return d


def request_out(r: CustomRequest, files: list[RequestFile], events: list[OrderEvent] | None = None,
                admin: bool = False, token: str = "") -> dict:
    q = f"?token={token}" if token else ""
    d = {"id": r.id, "status": r.status, "status_label": REQUEST_LABELS.get(r.status, r.status), "name": r.name,
         "phone": r.phone, "email": r.email, "title": r.title, "description": r.description, "size": r.size,
         "color": r.color, "qty": r.qty, "budget": f(r.budget), "quote_price": f(r.quote_price),
         "quote_minutes": r.quote_minutes, "quote_text": r.quote_text,
         "created_at": r.created_at.isoformat() if r.created_at else None,
         "files": [{"id": x.id, "name": x.name, "mime": x.mime, "size": x.size, "image": x.thumb is not None,
                    "url": f"/api/shop/requests/{r.id}/files/{x.id}{q}",
                    "thumb": f"/api/shop/requests/{r.id}/files/{x.id}/thumb{q}" if x.thumb is not None else None}
                   for x in files]}
    if admin:
        d.update(token=r.token, user_id=r.user_id, admin_note=r.admin_note, quote_cost=f(r.quote_cost),
                 quote_grams=f(r.quote_grams))
    if events is not None:
        d["events"] = [{"at": e.at.isoformat(), "who": e.who if admin else "", "status": e.status,
                        "status_label": REQUEST_LABELS.get(e.status or "", ""), "text": e.text}
                       for e in events if admin or e.status]
    return d


def check_token(given: str | None, real: str) -> bool:
    return bool(given) and hmac.compare_digest(given, real)


def can_see(user: User | None, owner_id: str | None, token: str | None, real_token: str) -> bool:
    return is_admin(user) or (user is not None and owner_id == user.id) or check_token(token, real_token)


def clean(s: str | None, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (s or "")).strip()[:n]


# ---------------------------------------------------------------- catalogue ----

@router.get("/info")
def info(db: Session = Depends(get_db)):
    s = shop_info(db)
    return {**s, "delivery": [{"id": d, "label": DELIVERY.get(d, d)} for d in s.get("delivery") or list(DELIVERY)],
            "order_statuses": ORDER_LABELS, "request_statuses": REQUEST_LABELS,
            "favicon_v": get_setting(db, "favicon").get("v", 0)}


def stats_since(db: Session):
    """Statistics start from this moment after «Сбросить статистику» (orders stay in the database)."""
    from datetime import datetime, timezone
    t = get_setting(db, "stats").get("since")
    return datetime.fromtimestamp(t, timezone.utc) if t else datetime(2000, 1, 1, tzinfo=timezone.utc)


def sold_counts(db: Session) -> dict[int, int]:
    rows = db.execute(select(OrderItem.product_id, func.sum(OrderItem.qty)).join(Order, Order.id == OrderItem.order_id)
                      .where(Order.status != "cancelled", OrderItem.product_id.is_not(None),
                             Order.created_at >= stats_since(db))
                      .group_by(OrderItem.product_id)).all()
    return {pid: int(n) for pid, n in rows}


def base_kg_price(p: Product, cs: dict) -> float:
    """₽/kg of the plastic the product price was calculated with."""
    inp = (p.calc or {}).get("input") or {}
    res = (p.calc or {}).get("result") or {}
    for v in (inp.get("kg_price"), res.get("kg_price")):
        if v and float(v) > 0:
            return float(v)
    mats = cs["materials"]
    return float(mats.get(product_material(p)) or mats.get("PLA") or next(iter(mats.values()), 1600))


def color_delta(p: Product, c: FilamentColor | None, cs: dict) -> tuple[int, float]:
    """(price difference for the buyer, cost difference) when the product is printed in colour c.
    The plastic price difference goes through the same waste, defect, markup and tax as in the calculator."""
    if not c or c.kg_price is None or not p.grams:
        return 0, 0.0
    g = float(p.grams)
    dcost = g * (1 + cs["waste_pct"] / 100) * (float(c.kg_price) - base_kg_price(p, cs)) / 1000
    dcost /= 1 - min(cs["fail_pct"], 90) / 100
    fees = min(cs["tax_pct"] + cs["commission_pct"], 90) / 100
    dprice = dcost * (1 + cs["markup_pct"] / 100) / (1 - fees)
    step = 10 if abs(dprice) >= 10 else 1
    return int(round(dprice / step) * step), round(dcost, 2)


def active_colors(db: Session) -> list[FilamentColor]:
    return list(db.execute(select(FilamentColor).where(FilamentColor.active.is_(True))
                           .order_by(FilamentColor.sort, FilamentColor.id)).scalars())


def allowed_colors(p: Product, active: list[FilamentColor]) -> list[FilamentColor]:
    """Colours a buyer can choose: the ones ticked for the product, or the whole palette if none are ticked."""
    if p.colors:
        by_id = {c.id: c for c in active}
        return [by_id[i] for i in p.colors if i in by_id]
    return list(active)


def color_popularity(db: Session) -> dict[str, int]:
    rows = db.execute(select(OrderItem.color, func.sum(OrderItem.qty)).join(Order, Order.id == OrderItem.order_id)
                      .where(Order.status != "cancelled", OrderItem.color != "").group_by(OrderItem.color)).all()
    return {name: int(n) for name, n in rows}


def ordered_colors(p: Product, cols: list[FilamentColor], pop: dict[str, int]) -> list[tuple[FilamentColor, str]]:
    """The standard colour (from the builder) first, then the 3 most ordered ones, then the rest."""
    std = next((c for c in cols if c.id == p.default_color), None)
    rest = [c for c in cols if c is not std]
    top = [c for c in sorted(rest, key=lambda c: -pop.get(c.name, 0)) if pop.get(c.name, 0) > 0][:3]
    if len(top) < 3:  # nothing ordered yet: the first colours of the palette
        top += [c for c in rest if c not in top][:3 - len(top)]
    out = [(std, "default")] if std else []
    out += [(c, "popular") for c in top]
    out += [(c, "") for c in rest if c not in top]
    return out


def media_out(pid: int, rows) -> list[dict]:
    return [{"id": m.id, "kind": m.kind, "mime": m.mime, "color_id": m.color_id, "name": m.name, "url": f"/api/shop/products/{pid}/media/{m.id}",
             "thumb": f"/api/shop/products/{pid}/media/{m.id}/thumb" if m.thumb else None} for m in rows]


def color_out(c: FilamentColor) -> dict:
    v = stamp(c.updated_at)
    return {"id": c.id, "name": c.name, "hex": c.hex, "hex2": c.hex2, "material": c.material, "note": c.note,
            "active": c.active, "sort": c.sort,
            "photo": f"/api/shop/colors/{c.id}/photo?v={v}" if c.photo else None,
            "thumb": f"/api/shop/colors/{c.id}/thumb?v={v}" if c.photo else None}


def product_material(p: Product) -> str:
    """Material from the calculator, or from a «Материал: …» line of the features."""
    if p.material:
        return p.material
    for ln in (p.features or "").splitlines():
        k, _, v = ln.partition(":")
        if k.strip().lower() in ("материал", "пластик") and v.strip():
            return v.strip()[:60]
    return ""


@router.get("/products")
def products(q: str = "", sort: str = Query("popular", pattern="^(popular|new|cheap|expensive)$"), category: str = "",
             in_stock: bool = False, pmin: float = Query(0, ge=0), pmax: float = Query(0, ge=0), color: int = 0,
             material: str = "", all: bool = False, ids: str = "", db: Session = Depends(get_db),
             user: User | None = Depends(current_user_optional)):
    show_hidden = all and is_admin(user)
    base = select(Product) if show_hidden else select(Product).where(Product.published.is_(True))
    every = list(db.execute(base).scalars())  # for the filter panel: categories, materials, price range
    sold = sold_counts(db)
    st = base
    if q.strip():
        like = f"%{q.strip()[:80]}%"
        st = st.where(or_(Product.title.ilike(like), Product.description.ilike(like), Product.category.ilike(like)))
    if category:
        st = st.where(Product.category == category)
    if in_stock:
        st = st.where(Product.stock > 0)
    if ids:  # «Избранное»
        want = [int(x) for x in ids.split(",")[:500] if x.strip().isdigit()]
        st = st.where(Product.id.in_(want))
    if pmin:
        st = st.where(Product.price >= pmin)
    if pmax:
        st = st.where(Product.price <= pmax)
    rows = list(db.execute(st).scalars())
    active = active_colors(db)
    act_ids = [c.id for c in active]
    eff = {p.id: [c.id for c in allowed_colors(p, active)] for p in every}
    if color:
        rows = [p for p in rows if color in eff.get(p.id, [])]
    if material:
        rows = [p for p in rows if product_material(p).lower() == material.lower()]
    key = {"popular": lambda p: (p.sort, -sold.get(p.id, 0), -p.views, -p.id),
           "new": lambda p: (-stamp(p.created_at), -p.id),
           "cheap": lambda p: (float(p.price), p.id), "expensive": lambda p: (-float(p.price), p.id)}[sort]
    rows.sort(key=key)
    cats: dict[str, int] = {}
    mats: dict[str, int] = {}
    for p in every:
        if p.category:
            cats[p.category] = cats.get(p.category, 0) + 1
        m = product_material(p)
        if m:
            mats[m] = mats.get(m, 0) + 1
    used = {c for ids_ in eff.values() for c in ids_}
    prices = [float(p.price) for p in every]
    # the photos and videos of each shown product, for the carousel in the tile (without the file bytes)
    media: dict[int, list] = {}
    if rows:
        for m in db.execute(select(ProductMedia.id, ProductMedia.product_id, ProductMedia.kind, ProductMedia.mime, ProductMedia.color_id, ProductMedia.name,
                                   ProductMedia.thumb.is_not(None).label("thumb"))
                            .where(ProductMedia.product_id.in_([p.id for p in rows]))
                            .order_by(ProductMedia.sort, ProductMedia.id)):
            media.setdefault(m.product_id, []).append(m)
    from .social import ratings
    rt = ratings(db, [p.id for p in rows])
    return {"items": [product_out(p, sold=sold.get(p.id, 0)) | {"material": product_material(p),
                                                                 "media": media_out(p.id, media.get(p.id, [])),
                                                                 "colors": eff.get(p.id, []),
                                                                 "default_color": p.default_color if p.default_color in eff.get(p.id, []) else None,
                                                                 "rating": rt.get(p.id, (0, 0))[0],
                                                                 "reviews": rt.get(p.id, (0, 0))[1]}
                      for p in rows],
            "categories": category_list(db, cats, show_hidden),
            "materials": [{"name": m, "count": n} for m, n in sorted(mats.items(), key=lambda x: -x[1])],
            "colors": [color_out(c) for c in db.execute(select(FilamentColor).where(FilamentColor.id.in_(used))
                                                        .order_by(FilamentColor.sort, FilamentColor.id)).scalars()],
            "price_min": min(prices) if prices else 0, "price_max": max(prices) if prices else 0,
            "in_stock": sum(1 for p in every if (p.stock or 0) > 0)}


def category_list(db: Session, counts: dict[str, int], admin: bool = False) -> list[dict]:
    """Groups for the shop front in the order set in the admin panel. A group nobody set up yet goes to the end."""
    out, seen = [], set()
    for c in db.execute(select(Category).order_by(Category.sort, Category.id)).scalars():
        seen.add(c.name)
        if (c.active or admin) and counts.get(c.name):
            out.append({"name": c.name, "count": counts[c.name], "active": c.active})
    for name, n in sorted(counts.items(), key=lambda x: -x[1]):
        if name not in seen:
            out.append({"name": name, "count": n, "active": True})
    return out


def published_product(db: Session, pid: int, user: User | None) -> Product:
    p = db.get(Product, pid)
    if not p or (not p.published and not is_admin(user)):
        raise HTTPException(404, "Товар не найден")
    return p


@router.get("/products/{pid}")
def product(pid: int, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    p = published_product(db, pid, user)
    p.views = (p.views or 0) + 1
    db.commit()
    media = db.execute(select(ProductMedia).where(ProductMedia.product_id == p.id)
                       .order_by(ProductMedia.sort, ProductMedia.id)).scalars()
    cs = calc_settings(db)
    cols = []
    for c, mark in ordered_colors(p, allowed_colors(p, active_colors(db)), color_popularity(db)):
        d, _ = color_delta(p, c, cs)
        cols.append(color_out(c) | {"delta": d, "price": max(float(p.price) + d, 1.0), "mark": mark})
    out = product_out(p, full=True, sold=sold_counts(db).get(p.id, 0)) | {
        "media": media_out(p.id, media), "color_list": cols, "material": product_material(p),
        "priced_colors": bool(p.grams)}  # weight known: the colour surcharge can be counted
    from .social import ratings
    out["rating"], out["reviews"] = ratings(db, [p.id]).get(p.id, (0, 0))
    if is_admin(user):
        out.update(item_id=p.item_id, features_raw=p.features, sort=p.sort, colors=list(p.colors or []),
                   default_color=p.default_color,
                   grams=f(p.grams), base_kg_price=base_kg_price(p, calc_settings(db)))
    return out


@router.get("/products/{pid}/{kind}")
def product_picture(pid: int, kind: str, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    if kind not in ("image", "thumb", "tile"):
        raise HTTPException(404, "Не найдено")
    p = published_product(db, pid, user)
    data = p.image if kind == "image" else (p.tile or p.thumb or p.image) if kind == "tile" else (p.thumb or p.image)
    if not data:
        raise HTTPException(404, "Нет картинки")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


# ---------------------------------------------------------------- orders ----

class LineIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1, le=999)
    note: str = Field(default="", max_length=300)
    color: int = 0
    colors: list[int] = Field(default_factory=list, max_length=8)  # «несколько цветов»: the price is confirmed later


class Contacts(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=160)


class OrderIn(Contacts):
    items: list[LineIn] = Field(min_length=1, max_length=100)
    delivery: str = Field(default="pickup", max_length=40)
    address: str = Field(default="", max_length=1000)
    comment: str = Field(default="", max_length=3000)
    consent: bool = False
    terms: bool = False
    payment: str = Field(default="on_delivery", max_length=20)


PAYMENT = {"on_delivery": "при получении"}  # online payment is not available yet


def check_consent(consent, terms) -> None:
    if str(consent).lower() not in ("true", "1", "on", "yes"):
        raise HTTPException(400, "Нужно согласие на обработку персональных данных")
    if str(terms).lower() not in ("true", "1", "on", "yes"):
        raise HTTPException(400, "Нужно согласиться с условиями заказа")


def check_contacts(c: Contacts) -> None:
    if not clean(c.phone, 60) and not clean(c.email, 160):
        raise HTTPException(400, "Укажи телефон или почту, чтобы мы могли связаться")
    if c.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", c.email.strip()):
        raise HTTPException(400, "Похоже, в почте ошибка")


@router.post("/orders")
def create_order(data: OrderIn, request: Request, db: Session = Depends(get_db),
                 user: User | None = Depends(current_user_optional)):
    rate_limit("order:" + client_ip(request), 20, 3600)
    check_contacts(data)
    check_consent(data.consent, data.terms)
    if data.payment not in PAYMENT:
        raise HTTPException(400, "Онлайн-оплата пока недоступна: выбери оплату при получении")
    shop = shop_info(db)
    if data.delivery not in (shop.get("delivery") or list(DELIVERY)):
        raise HTTPException(400, "Неизвестный способ доставки")
    if data.delivery != "pickup" and not data.address.strip():
        raise HTTPException(400, "Укажи адрес доставки")
    o = Order(token=secrets.token_urlsafe(18), user_id=user.id if user else None, status="new",
              name=clean(data.name, 160), phone=clean(data.phone, 60), email=clean(data.email, 160),
              delivery=data.delivery, address=clean(data.address, 1000), comment=clean(data.comment, 3000),
              admin_note="", total=0, cost=0, print_minutes=0, grams=0, paid=False)
    db.add(o)
    db.flush()
    total = cost = Decimal(0)
    minutes, grams = 0, Decimal(0)
    lines = []
    cs = calc_settings(db)
    active = active_colors(db)
    for line in data.items:
        p = db.get(Product, line.product_id, with_for_update=True)
        if not p or not p.published:
            raise HTTPException(400, "Одного из товаров уже нет в магазине. Обнови корзину.")
        color_name, c, multi = "", None, []
        allowed = allowed_colors(p, active)
        if len(set(line.colors)) >= 2:
            by_id = {x.id: x for x in allowed}
            multi = [by_id[i] for i in dict.fromkeys(line.colors) if i in by_id]
            if len(multi) != len(set(line.colors)):
                raise HTTPException(400, f"Один из цветов для «{p.title}» больше недоступен")
            color_name = " + ".join(x.name for x in multi)[:120]
        elif allowed:
            if line.color:
                c = next((x for x in allowed if x.id == line.color), None)
                if not c:
                    raise HTTPException(400, f"Выбери цвет для «{p.title}»")
            else:  # no choice made: the standard colour, or the first one offered
                c = next((x for x in allowed if x.id == p.default_color), allowed[0])
            color_name = c.name
        if multi:  # estimate: the dearest of the chosen colours; the admin sets the real price after the slicer
            dprice, dcost = max((color_delta(p, x, cs) for x in multi), key=lambda d: d[0])
        else:
            dprice, dcost = color_delta(p, c, cs)
        price = max(p.price + Decimal(dprice), Decimal(1))
        unit_cost = (p.cost or 0) + Decimal(str(dcost))
        from_stock = 0 if multi else min(p.stock or 0, line.qty)  # a multicolour piece is always printed
        p.stock = (p.stock or 0) - from_stock
        to_print = line.qty - from_stock
        db.add(OrderItem(order_id=o.id, product_id=p.id, title=p.title, price=price, cost=unit_cost, qty=line.qty,
                         print_minutes=p.print_minutes or 0, grams=p.grams or 0, note=clean(line.note, 300),
                         from_stock=from_stock, color=color_name, price_pending=bool(multi)))
        lines.append(f"• {p.title}{' (' + color_name + ')' if color_name else ''} × {line.qty}"
                     + (" — несколько цветов, цену подтвердить после слайсера" if multi else ""))
        total += price * line.qty
        cost += unit_cost * line.qty
        minutes += (p.print_minutes or 0) * to_print
        grams += (p.grams or 0) * to_print
    if shop.get("min_order") and total < Decimal(str(shop["min_order"])):
        raise HTTPException(400, f"Минимальная сумма заказа {shop['min_order']} ₽")
    o.total, o.cost, o.print_minutes, o.grams = total, cost, minutes, grams
    add_event(db, order_id=o.id, who_=o.name, status="new", text=f"Заказ оформлен на сайте. Оплата: {PAYMENT[data.payment]}. " + CONSENT_TEXT)
    db.commit()
    notify(f"🛒 Новый заказ №{o.id} на {total:.0f} ₽ от {o.name} {o.phone or o.email}\n" + "\n".join(lines))
    return {"id": o.id, "token": o.token, "total": f(total)}


def load_order(db: Session, oid: int) -> Order:
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Заказ не найден")
    return o


def order_lines(db: Session, oid: int) -> list[OrderItem]:
    return list(db.execute(select(OrderItem).where(OrderItem.order_id == oid).order_by(OrderItem.id)).scalars())


def order_events(db: Session, oid: int) -> list[OrderEvent]:
    return list(db.execute(select(OrderEvent).where(OrderEvent.order_id == oid).order_by(OrderEvent.at, OrderEvent.id)).scalars())


@router.get("/orders/mine")
def my_orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(200)).scalars()
    return [order_out(o, order_lines(db, o.id)) | {"token": o.token} for o in rows]


@router.get("/orders/{oid}")
def get_order(oid: int, token: str = "", db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    o = load_order(db, oid)
    if not can_see(user, o.user_id, token, o.token):
        raise HTTPException(404, "Заказ не найден")
    return order_out(o, order_lines(db, o.id), order_events(db, o.id))


def return_stock(db: Session, o: Order) -> None:
    for i in order_lines(db, o.id):
        if i.from_stock and i.product_id:
            p = db.get(Product, i.product_id)
            if p:
                p.stock = (p.stock or 0) + i.from_stock
            i.from_stock = 0


@router.post("/orders/{oid}/cancel")
def cancel_order(oid: int, token: str = "", db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    o = load_order(db, oid)
    if not can_see(user, o.user_id, token, o.token):
        raise HTTPException(404, "Заказ не найден")
    if o.status != "new":
        raise HTTPException(400, "Заказ уже в работе. Чтобы отменить, свяжись с магазином.")
    return_stock(db, o)
    o.status = "cancelled"
    o.closed_at = func.now()
    add_event(db, order_id=o.id, who_=o.name, status="cancelled", text="Покупатель отменил заказ")
    db.commit()
    notify(f"❌ Заказ №{o.id} отменён покупателем")
    return {"ok": True}


# ---------------------------------------------------------------- custom requests ----

def file_ok(name: str) -> bool:
    return "." in name and name[name.rfind("."):].lower() in ALLOWED_EXT


@router.post("/requests")
async def create_request(request: Request, name: str = Form(..., max_length=160), phone: str = Form("", max_length=60),
                         email: str = Form("", max_length=160), title: str = Form("", max_length=300),
                         description: str = Form(..., min_length=3, max_length=5000), size: str = Form("", max_length=160),
                         color: str = Form("", max_length=160), qty: int = Form(1, ge=1, le=10000),
                         budget: str = Form("", max_length=20),
                         consent: str = Form(""), terms: str = Form(""), files: list[UploadFile] = File(default=[]),
                         db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    rate_limit("req:" + client_ip(request), 10, 3600)
    if int(request.headers.get("content-length") or 0) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Слишком большие файлы (вместе больше {settings.MAX_UPLOAD_MB} МБ)")
    check_contacts(Contacts(name=name, phone=phone, email=email))
    check_consent(consent, terms)
    files = [x for x in files if x.filename]
    if len(files) > settings.MAX_REQUEST_FILES:
        raise HTTPException(400, f"Не больше {settings.MAX_REQUEST_FILES} файлов")
    for x in files:
        if not file_ok(x.filename):
            raise HTTPException(400, f"Файл «{x.filename}» не подходит. Можно картинки, STL, 3MF, OBJ, STEP, PDF, ZIP.")
    b = pricing._num(budget, 0) or None
    r = CustomRequest(token=secrets.token_urlsafe(18), user_id=user.id if user else None, status="new",
                      name=clean(name, 160), phone=clean(phone, 60), email=clean(email, 160), title=clean(title, 300),
                      description=clean(description, 5000), size=clean(size, 160), color=clean(color, 160), qty=qty,
                      budget=b, quote_text="", admin_note="")
    db.add(r)
    db.flush()
    for x in files:
        data = await x.read()
        thumb = None
        if (x.content_type or "").startswith("image/"):
            try:
                thumb = jpeg(data, 480, 80)
            except Exception:  # noqa: BLE001  (HEIC and broken pictures: keep the file, no preview)
                thumb = None
        db.add(RequestFile(request_id=r.id, name=clean(x.filename, 300), mime=(x.content_type or "application/octet-stream")[:120],
                           size=len(data), data=data, thumb=thumb))
    add_event(db, request_id=r.id, who_=r.name, status="new", text="Заявка отправлена с сайта. " + CONSENT_TEXT)
    db.commit()
    notify(f"💡 Новая заявка на печать №{r.id} от {r.name} {r.phone or r.email}: {r.title or r.description[:80]} (файлов: {len(files)})")
    return {"id": r.id, "token": r.token}


def load_request(db: Session, rid: int) -> CustomRequest:
    r = db.get(CustomRequest, rid)
    if not r:
        raise HTTPException(404, "Заявка не найдена")
    return r


def request_files(db: Session, rid: int) -> list[RequestFile]:
    return list(db.execute(select(RequestFile).where(RequestFile.request_id == rid).order_by(RequestFile.id)).scalars())


def request_events(db: Session, rid: int) -> list[OrderEvent]:
    return list(db.execute(select(OrderEvent).where(OrderEvent.request_id == rid).order_by(OrderEvent.at, OrderEvent.id)).scalars())


@router.get("/requests/mine")
def my_requests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(CustomRequest).where(CustomRequest.user_id == user.id).order_by(CustomRequest.id.desc()).limit(200)).scalars()
    return [request_out(r, request_files(db, r.id)) | {"token": r.token} for r in rows]


@router.get("/requests/{rid}")
def get_request(rid: int, token: str = "", db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    r = load_request(db, rid)
    if not can_see(user, r.user_id, token, r.token):
        raise HTTPException(404, "Заявка не найдена")
    return request_out(r, request_files(db, r.id), request_events(db, r.id), token=token if check_token(token, r.token) else "")


@router.get("/requests/{rid}/files/{fid}")
def get_request_file(rid: int, fid: int, token: str = "", db: Session = Depends(get_db),
                     user: User | None = Depends(current_user_optional)):
    return _file(rid, fid, token, db, user, thumb=False)


@router.get("/requests/{rid}/files/{fid}/thumb")
def get_request_thumb(rid: int, fid: int, token: str = "", db: Session = Depends(get_db),
                      user: User | None = Depends(current_user_optional)):
    return _file(rid, fid, token, db, user, thumb=True)


def _file(rid, fid, token, db, user, thumb):
    r = load_request(db, rid)
    x = db.get(RequestFile, fid)
    if not x or x.request_id != r.id or not can_see(user, r.user_id, token, r.token):
        raise HTTPException(404, "Файл не найден")
    if thumb:
        if x.thumb is None:
            raise HTTPException(404, "Нет картинки")
        return Response(x.thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
    inline = x.mime.startswith("image/") and x.mime != "image/svg+xml"
    safe = re.sub(r'[^\w.\- ]', "_", x.name)
    return Response(x.data, media_type=x.mime if inline else "application/octet-stream",
                    headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{safe}"',
                             "Cache-Control": "private, max-age=0"})


class AcceptIn(BaseModel):
    delivery: str = Field(default="pickup", max_length=40)
    address: str = Field(default="", max_length=1000)
    comment: str = Field(default="", max_length=3000)


@router.post("/requests/{rid}/accept")
def accept_quote(rid: int, data: AcceptIn, token: str = "", db: Session = Depends(get_db),
                 user: User | None = Depends(current_user_optional)):
    """The customer agrees to the admin's price: the request becomes an order."""
    r = load_request(db, rid)
    if not can_see(user, r.user_id, token, r.token):
        raise HTTPException(404, "Заявка не найдена")
    if r.status != "quoted" or r.quote_price is None:
        raise HTTPException(400, "Цену по заявке ещё не назвали")
    if data.delivery not in DELIVERY:
        raise HTTPException(400, "Неизвестный способ доставки")
    o = Order(token=secrets.token_urlsafe(18), user_id=r.user_id or (user.id if user else None), status="new",
              name=r.name, phone=r.phone, email=r.email, delivery=data.delivery, address=clean(data.address, 1000),
              comment=clean(data.comment, 3000), admin_note="", total=r.quote_price, cost=r.quote_cost or 0,
              print_minutes=r.quote_minutes or 0, grams=r.quote_grams or 0, paid=False, request_id=r.id)
    db.add(o)
    db.flush()
    qty = max(1, r.qty or 1)
    db.add(OrderItem(order_id=o.id, product_id=None, title=("На заказ: " + (r.title or r.description[:60]))[:300],
                     price=(r.quote_price / qty).quantize(Decimal("0.01")), cost=((r.quote_cost or 0) / qty), qty=qty,
                     print_minutes=round((r.quote_minutes or 0) / qty), grams=(r.quote_grams or 0) / qty,
                     note=clean(r.color, 300)))
    r.status = "ordered"
    add_event(db, request_id=r.id, who_=r.name, status="ordered", text=f"Покупатель согласился, заказ №{o.id}")
    add_event(db, order_id=o.id, who_=r.name, status="new", text=f"Заказ по заявке №{r.id}")
    db.commit()
    notify(f"✅ Заявка №{r.id} согласована, заказ №{o.id} на {r.quote_price:.0f} ₽")
    return {"id": o.id, "token": o.token}


# ---------------------------------------------------------------- calculator ----

class CalcIn(BaseModel):
    material: str = Field(default="PLA", max_length=60)
    grams: float = Field(default=0, ge=0, le=100000)
    hours: float = Field(default=0, ge=0, le=10000)
    minutes: float = Field(default=0, ge=0, le=100000)
    pieces: int = Field(default=1, ge=1, le=10000)
    finish_min: float = Field(default=0, ge=0, le=10000)
    extras: float = Field(default=0, ge=0, le=10_000_000)
    markup_pct: Optional[float] = Field(default=None, ge=0, le=10000)
    kg_price: float = Field(default=0, ge=0, le=1_000_000)  # own price of the spool, ₽/kg (0 = from settings)


@router.post("/calc")
def calc(data: CalcIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только для администратора магазина")
    return pricing.calc(data.model_dump(), get_setting(db, "calc"))
