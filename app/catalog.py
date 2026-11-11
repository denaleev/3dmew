"""Product photos and videos, the filament colour palette and the feedback form."""
import logging
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Category, FilamentColor, Feedback, Product, ProductMedia, User
from .security import client_ip, current_admin, current_user_optional, is_admin, rate_limit
from .shop import clean, color_out, jpeg, media_out, notify, published_product, shop_info, stamp

log = logging.getLogger("kartochki.catalog")
public = APIRouter(prefix="/api/shop")
admin = APIRouter(prefix="/api/admin")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp"}
VIDEO_MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
CACHE = {"Cache-Control": "public, max-age=604800"}


def ext(name: str) -> str:
    m = re.search(r"\.[A-Za-z0-9]+$", name or "")
    return m.group(0).lower() if m else ""


def ranged(request: Request, data: bytes, mime: str) -> Response:
    """Serve bytes with HTTP Range support: Safari plays video only when the server answers 206."""
    size = len(data)
    rng = request.headers.get("range", "")
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return Response(data, media_type=mime, headers={**CACHE, "Accept-Ranges": "bytes"})
    if m.group(1) == "":
        start, end = max(0, size - int(m.group(2))), size - 1
    else:
        start = int(m.group(1))
        end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
    if start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    return Response(data[start:end + 1], status_code=206, media_type=mime,
                    headers={**CACHE, "Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{size}"})


# ---------------------------------------------------------------- media ----

@public.get("/products/{pid}/media/{mid}")
def get_media(pid: int, mid: int, request: Request, db: Session = Depends(get_db),
              user: User | None = Depends(current_user_optional)):
    published_product(db, pid, user)
    m = db.get(ProductMedia, mid)
    if not m or m.product_id != pid:
        raise HTTPException(404, "Не найдено")
    return ranged(request, m.data, m.mime)


@public.get("/products/{pid}/media/{mid}/thumb")
def get_media_thumb(pid: int, mid: int, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    published_product(db, pid, user)
    m = db.get(ProductMedia, mid)
    if not m or m.product_id != pid or not m.thumb:
        raise HTTPException(404, "Не найдено")
    return Response(m.thumb, media_type="image/jpeg", headers=CACHE)


@admin.post("/products/{pid}/media")
async def add_media(pid: int, files: list[UploadFile] = File(...), color_id: int | None = Form(None),
                    db: Session = Depends(get_db), _: User = Depends(current_admin)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Товар не найден")
    if color_id is not None and not db.get(FilamentColor, color_id):
        color_id = None
    last = db.execute(select(func.max(ProductMedia.sort)).where(ProductMedia.product_id == pid)).scalar() or 0
    added = []
    for f in files[:20]:
        e = ext(f.filename or "")
        data = await f.read()
        if e in VIDEO_MIME or (f.content_type or "").startswith("video/"):
            if len(data) > settings.MAX_VIDEO_MB * 1024 * 1024:
                raise HTTPException(413, f"Видео «{f.filename}» больше {settings.MAX_VIDEO_MB} МБ")
            m = ProductMedia(product_id=pid, kind="video", mime=VIDEO_MIME.get(e, f.content_type or "video/mp4"),
                             name=(f.filename or "video")[:300], size=len(data), data=data)
        elif e in IMAGE_EXT or (f.content_type or "").startswith("image/"):
            if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(413, f"Фото «{f.filename}» больше {settings.MAX_UPLOAD_MB} МБ")
            try:
                big = jpeg(data, 1800, 88)
            except Exception:  # noqa: BLE001
                raise HTTPException(400, f"Не получилось открыть «{f.filename}» как картинку")
            m = ProductMedia(product_id=pid, kind="image", mime="image/jpeg", name=(f.filename or "photo")[:300],
                             size=len(big), data=big, thumb=jpeg(data, 400, 82))
        else:
            raise HTTPException(400, f"«{f.filename}»: можно фото (JPG, PNG, WEBP) или видео (MP4, MOV, WEBM)")
        last += 1
        m.sort, m.color_id = last, color_id
        db.add(m)
        added.append(m)
    db.commit()
    rows = db.execute(select(ProductMedia).where(ProductMedia.product_id == pid)
                      .order_by(ProductMedia.sort, ProductMedia.id)).scalars()
    return {"media": media_out(pid, rows)}


class MediaOrder(BaseModel):
    ids: list[int] = Field(max_length=200)


@admin.put("/products/{pid}/media")
def order_media(pid: int, data: MediaOrder, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    rows = {m.id: m for m in db.execute(select(ProductMedia).where(ProductMedia.product_id == pid)).scalars()}
    for i, mid in enumerate(data.ids):
        if mid in rows:
            rows[mid].sort = i + 1
    db.commit()
    return {"ok": True}


class MediaColor(BaseModel):
    color_id: int | None = None


@admin.patch("/products/{pid}/media/{mid}")
def media_color(pid: int, mid: int, data: MediaColor, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """Which plastic the product is printed in on this photo (none = a general photo)."""
    m = db.get(ProductMedia, mid)
    if not m or m.product_id != pid:
        raise HTTPException(404, "Не найдено")
    m.color_id = data.color_id if data.color_id and db.get(FilamentColor, data.color_id) else None
    db.commit()
    return {"id": m.id, "color_id": m.color_id}


@admin.post("/products/{pid}/media/{mid}/main")
def media_to_main(pid: int, mid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """Make a photo the main picture of the product (the one shown in the catalogue)."""
    p, m = db.get(Product, pid), db.get(ProductMedia, mid)
    if not p or not m or m.product_id != pid or m.kind != "image":
        raise HTTPException(404, "Не найдено")
    old_image, old_thumb = p.image, p.thumb
    p.image, p.thumb = m.data, jpeg(m.data, 520, 82)
    if old_image:  # the old main picture stays in the gallery
        m.data, m.thumb, m.size, m.name = old_image, old_thumb or jpeg(old_image, 400, 82), len(old_image), "карточка"
        m.color_id = None
    else:
        db.delete(m)
    db.commit()
    return {"ok": True}


@admin.delete("/products/{pid}/media/{mid}", status_code=204)
def delete_media(pid: int, mid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    m = db.get(ProductMedia, mid)
    if m and m.product_id == pid:
        db.delete(m)
        db.commit()
    return Response(status_code=204)


@admin.put("/products/{pid}/image")
async def replace_main_image(pid: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                             _: User = Depends(current_admin)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Товар не найден")
    data = await file.read()
    try:
        p.image, p.thumb = jpeg(data, 1600, 88), jpeg(data, 520, 82)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Это не картинка")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- colours ----

@public.get("/colors")
def colors(db: Session = Depends(get_db)):
    rows = db.execute(select(FilamentColor).where(FilamentColor.active.is_(True))
                      .order_by(FilamentColor.sort, FilamentColor.id)).scalars()
    return [color_out(c) for c in rows]


@public.get("/colors/{cid}/{kind}")
def color_photo(cid: int, kind: str, db: Session = Depends(get_db)):
    c = db.get(FilamentColor, cid)
    if kind not in ("photo", "thumb") or not c or not c.photo:
        raise HTTPException(404, "Нет фото")
    return Response(c.photo if kind == "photo" else (c.thumb or c.photo), media_type="image/jpeg", headers=CACHE)


@admin.get("/colors")
def admin_colors(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    rows = list(db.execute(select(FilamentColor).order_by(FilamentColor.sort, FilamentColor.id)).scalars())
    used: dict[int, int] = {}
    for cols in db.execute(select(Product.colors).where(Product.colors.is_not(None))).scalars():
        for c in cols or []:
            used[c] = used.get(c, 0) + 1
    return [color_out(c) | {"used": used.get(c.id, 0), "kg_price": float(c.kg_price) if c.kg_price is not None else None}
            for c in rows]


HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def apply_color(c: FilamentColor, name, hex_, hex2, material, note, active, sort, kg_price=None) -> None:
    if kg_price is not None:
        v = str(kg_price).replace(",", ".").replace(" ", "")
        if v == "":
            c.kg_price = None
        else:
            try:
                c.kg_price = round(float(v), 2)
            except ValueError:
                raise HTTPException(400, "Цена пластика — число, ₽ за кг")
            if not 0 < c.kg_price < 100000:
                raise HTTPException(400, "Цена пластика: от 1 до 99 999 ₽ за кг")
    if name is not None:
        if not clean(name, 120):
            raise HTTPException(400, "Назови цвет")
        c.name = clean(name, 120)
    if hex_ is not None:
        if not HEX.match(hex_):
            raise HTTPException(400, "Цвет в формате #RRGGBB")
        c.hex = hex_.lower()
    if hex2 is not None:
        if hex2 and not HEX.match(hex2):
            raise HTTPException(400, "Второй цвет в формате #RRGGBB")
        c.hex2 = hex2.lower()
    if material is not None:
        c.material = clean(material, 60)
    if note is not None:
        c.note = clean(note, 300)
    if active is not None:
        c.active = str(active).lower() in ("1", "true", "on", "yes")
    if sort is not None and str(sort).lstrip("-").isdigit():
        c.sort = int(sort)


async def color_photo_in(c: FilamentColor, photo: UploadFile | None) -> None:
    if photo is None or not photo.filename:
        return
    data = await photo.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "Фото слишком большое")
    try:
        c.photo, c.thumb = jpeg(data, 1200, 86), jpeg(data, 240, 82)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Это не картинка")


@admin.post("/colors")
async def create_color(name: str = Form(...), hex: str = Form("#cccccc"), hex2: str = Form(""), material: str = Form(""),
                       note: str = Form(""), active: str = Form("1"), sort: str = Form("0"), kg_price: str = Form(""),
                       photo: UploadFile | None = File(None), db: Session = Depends(get_db),
                       _: User = Depends(current_admin)):
    c = FilamentColor()
    apply_color(c, name, hex, hex2, material, note, active, sort, kg_price)
    await color_photo_in(c, photo)
    db.add(c)
    db.commit()
    return color_out(c) | {"kg_price": float(c.kg_price) if c.kg_price is not None else None}


@admin.patch("/colors/{cid}")
async def update_color(cid: int, name: str | None = Form(None), hex: str | None = Form(None), hex2: str | None = Form(None),
                       material: str | None = Form(None), note: str | None = Form(None), active: str | None = Form(None),
                       sort: str | None = Form(None), kg_price: str | None = Form(None),
                       photo: UploadFile | None = File(None),
                       drop_photo: str = Form(""), db: Session = Depends(get_db), _: User = Depends(current_admin)):
    c = db.get(FilamentColor, cid)
    if not c:
        raise HTTPException(404, "Цвет не найден")
    apply_color(c, name, hex, hex2, material, note, active, sort, kg_price)
    if drop_photo:
        c.photo = c.thumb = None
    await color_photo_in(c, photo)
    db.commit()
    return color_out(c) | {"kg_price": float(c.kg_price) if c.kg_price is not None else None}


@admin.delete("/colors/{cid}", status_code=204)
def delete_color(cid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    c = db.get(FilamentColor, cid)
    if c:
        for p in db.execute(select(Product).where(Product.colors.is_not(None))).scalars():
            if cid in (p.colors or []):
                p.colors = [x for x in p.colors if x != cid]
        db.delete(c)
        db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- categories ----

class CategoryIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    sort: int | None = None
    active: bool | None = None


def category_counts(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Product.category, func.count()).where(Product.category != "")
                           .group_by(Product.category)).all())


@admin.get("/categories")
def admin_categories(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """All groups, also the ones products use but nobody set up yet (they are created here)."""
    counts = category_counts(db)
    have = {c.name for c in db.execute(select(Category)).scalars()}
    top = db.execute(select(func.max(Category.sort))).scalar() or 0
    for name in sorted(set(counts) - have):
        top += 10
        db.add(Category(name=name, sort=top, icon=""))
    db.commit()
    return [{"id": c.id, "name": c.name, "sort": c.sort, "active": c.active, "count": counts.get(c.name, 0)}
            for c in db.execute(select(Category).order_by(Category.sort, Category.id)).scalars()]


def category_name(db: Session, name: str, cid: int = 0) -> str:
    name = clean(name, 80)
    if not name:
        raise HTTPException(400, "Назови категорию")
    other = db.execute(select(Category).where(func.lower(Category.name) == name.lower())).scalar_one_or_none()
    if other and other.id != cid:
        raise HTTPException(409, f"Категория «{other.name}» уже есть")
    return name


@admin.post("/categories")
def create_category(data: CategoryIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    name = category_name(db, data.name or "")
    sort = data.sort if data.sort is not None else (db.execute(select(func.max(Category.sort))).scalar() or 0) + 10
    c = Category(name=name, sort=sort, active=True if data.active is None else data.active, icon="")
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "sort": c.sort, "active": c.active, "count": 0}


@admin.patch("/categories/{cid}")
def update_category(cid: int, data: CategoryIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """Renaming moves all products of the group to the new name."""
    c = db.get(Category, cid)
    if not c:
        raise HTTPException(404, "Категория не найдена")
    if data.name is not None:
        name = category_name(db, data.name, cid)
        if name != c.name:
            for p in db.execute(select(Product).where(Product.category == c.name)).scalars():
                p.category = name
            c.name = name
    if data.sort is not None:
        c.sort = data.sort
    if data.active is not None:
        c.active = data.active
    db.commit()
    return {"id": c.id, "name": c.name, "sort": c.sort, "active": c.active, "count": category_counts(db).get(c.name, 0)}


class CategoryOrder(BaseModel):
    ids: list[int] = Field(max_length=500)


@admin.put("/categories/order")
def order_categories(data: CategoryOrder, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    for i, cid in enumerate(data.ids, 1):
        c = db.get(Category, cid)
        if c:
            c.sort = i * 10
    db.commit()
    return {"ok": True}


@admin.delete("/categories/{cid}", status_code=204)
def delete_category(cid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """The products of the group stay, they just go without a group."""
    c = db.get(Category, cid)
    if c:
        for p in db.execute(select(Product).where(Product.category == c.name)).scalars():
            p.category = ""
        db.delete(c)
        db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- feedback ----

def send_mail(subject: str, body: str, reply_to: str = "") -> bool:
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD and settings.FEEDBACK_EMAIL):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Сайт 3DМяу", settings.SMTP_USER))
    msg["To"] = settings.FEEDBACK_EMAIL
    if reply_to and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", reply_to):
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, 465, context=ssl.create_default_context(), timeout=20) as s:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("e-mail: %s", e)
        return False


def mail_feedback(fid: int, subject: str, body: str, reply_to: str) -> None:
    from .db import SessionLocal

    if send_mail(subject, body, reply_to):
        with SessionLocal() as db:
            fb = db.get(Feedback, fid)
            if fb:
                fb.emailed = True
                db.commit()


class FeedbackIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=3, max_length=5000)
    consent: bool = False


@public.post("/feedback")
def feedback(data: FeedbackIn, request: Request, db: Session = Depends(get_db)):
    rate_limit("fb:" + client_ip(request), 10, 3600)
    if not data.consent:
        raise HTTPException(400, "Нужно согласие на обработку персональных данных")
    fb = Feedback(name=clean(data.name, 160), contact=clean(data.contact, 200), text=clean(data.text, 5000))
    db.add(fb)
    db.commit()
    shop = shop_info(db)
    body = f"Сообщение с сайта {shop.get('name', '')} (№{fb.id})\n\nИмя: {fb.name}\nКак связаться: {fb.contact}\n\n{fb.text}\n"
    threading.Thread(target=mail_feedback, args=(fb.id, f"Обратная связь №{fb.id}: {fb.name}", body, fb.contact),
                     daemon=True).start()
    notify(f"✉️ Обратная связь №{fb.id} от {fb.name} ({fb.contact}):\n{fb.text[:1500]}", mail=False)
    return {"ok": True, "id": fb.id}


@admin.get("/feedback")
def list_feedback(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    rows = db.execute(select(Feedback).order_by(Feedback.id.desc()).limit(500)).scalars()
    return {"items": [{"id": x.id, "name": x.name, "contact": x.contact, "text": x.text, "done": x.done,
                       "emailed": x.emailed, "created_at": x.created_at.isoformat() if x.created_at else None}
                      for x in rows],
            "mail_configured": bool(settings.SMTP_USER and settings.SMTP_PASSWORD), "email": settings.FEEDBACK_EMAIL}


class FeedbackPatch(BaseModel):
    done: bool


@admin.patch("/feedback/{fid}")
def patch_feedback(fid: int, data: FeedbackPatch, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    fb = db.get(Feedback, fid)
    if not fb:
        raise HTTPException(404, "Не найдено")
    fb.done = data.done
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- favicon ----

NO_CACHE = {"Cache-Control": "no-cache"}  # the browser asks again every time, so a new icon shows at once


def _favicon(db: Session) -> dict:
    from .models import ShopSetting
    row = db.get(ShopSetting, "favicon")
    return dict(row.data) if row and row.data else {}


@public.get("/favicon/{size}.png", include_in_schema=False)
def favicon(size: int, db: Session = Depends(get_db)):
    import base64
    data = _favicon(db).get(str(size if size in (64, 180, 512) else 64))
    if not data:
        name = {180: "logo-160.png", 512: "logo-512.png"}.get(size, "logo-64.png")
        return Response((settings.STATIC_DIR / "img" / name).read_bytes(), media_type="image/png",
                        headers=NO_CACHE)
    return Response(base64.b64decode(data), media_type="image/png", headers=NO_CACHE)


@admin.put("/favicon")
async def set_favicon(file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """Own browser-tab icon: any picture, it is cropped to a square and saved as PNG 64/180/512 px."""
    import base64
    import io
    from PIL import Image, ImageOps
    from .models import ShopSetting
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Картинка больше 10 МБ")
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGBA")
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Это не картинка (подойдёт PNG, JPG, WEBP, ICO)")
    side = min(im.size)
    im = im.crop(((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2))
    out = {}
    for s in (64, 180, 512):
        b = io.BytesIO()
        im.resize((s, s), Image.LANCZOS).save(b, "PNG", optimize=True)
        out[str(s)] = base64.b64encode(b.getvalue()).decode()
    import time
    out["v"] = int(time.time() * 1000)
    row = db.get(ShopSetting, "favicon") or ShopSetting(key="favicon", data={})
    row.data = out
    db.add(row)
    db.commit()
    return {"ok": True, "v": out["v"]}


@admin.delete("/favicon", status_code=204)
def reset_favicon(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    from .models import ShopSetting
    import time
    row = db.get(ShopSetting, "favicon") or ShopSetting(key="favicon", data={})
    row.data = {"v": int(time.time() * 1000)}  # a new version, so the pages ask for the standard icon again
    db.add(row)
    db.commit()
    return Response(status_code=204)
