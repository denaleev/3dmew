"""Business cards and booklets: the library of cut-out product photos, saved layouts and QR codes."""
import io
from typing import Annotated, Any, Optional

import segno
from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, defer

from .config import settings
from .db import get_db
from .models import Cutout, ShopSetting, User
from .security import current_admin
from .shop import clean, get_setting

router = APIRouter(prefix="/api")
ID = r"^[A-Za-z0-9_-]{1,40}$"
THUMB = 320
LAYOUT_KINDS = ("card", "booklet")


def read_png(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Это не картинка")
    return img


def as_png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def make_thumb(c: Cutout) -> bytes:
    img = Image.open(io.BytesIO(c.png))
    c.width, c.height = img.size
    img = img.convert("RGBA")
    img.thumbnail((THUMB, THUMB), Image.LANCZOS)
    return as_png(img)


def cutout_out(c: Cutout) -> dict:
    v = int(c.updated_at.timestamp()) if c.updated_at else 0
    return {"id": c.id, "name": c.name, "source": c.source, "w": c.width, "h": c.height,
            "t": c.updated_at.isoformat() if c.updated_at else None,
            "png": f"/api/admin/cutouts/{c.id}/png?v={v}", "thumb": f"/api/admin/cutouts/{c.id}/thumb?v={v}"}


async def upload_png(request: Request, up: UploadFile) -> tuple[bytes, Image.Image]:
    if int(request.headers.get("content-length") or 0) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Слишком большой файл (больше {settings.MAX_UPLOAD_MB} МБ)")
    data = await up.read()
    img = read_png(data)
    if img.format != "PNG":  # keep the transparency: anything else is converted
        data = as_png(img.convert("RGBA"))
    return data, img


# ---------------------------------------------------------------- the card builder saves its cut-outs ----

@router.put("/cutouts/{source}")
async def save_cutout(source: Annotated[str, Path(pattern=ID)], request: Request, png: UploadFile = File(...),
                      name: str = Form("", max_length=300), user: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Called by the card builder when a card with a cut-out photo is saved to the library (one row per card)."""
    data, img = await upload_png(request, png)
    c = db.execute(select(Cutout).where(Cutout.user_id == user.id, Cutout.source == source)).scalar_one_or_none()
    c = c or Cutout(user_id=user.id, source=source)
    c.name, c.png, c.thumb = clean(name, 300) or "Без названия", data, None
    c.width, c.height = img.size
    db.add(c)
    db.commit()
    return cutout_out(c)


# ---------------------------------------------------------------- admin: library ----

@router.get("/admin/cutouts")
def list_cutouts(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    rows = db.execute(select(Cutout).options(defer(Cutout.png), defer(Cutout.thumb)).order_by(Cutout.updated_at.desc(), Cutout.id.desc())).scalars()
    return [cutout_out(c) for c in rows]


@router.post("/admin/cutouts")
async def add_cutout(request: Request, file: UploadFile = File(...), name: str = Form("", max_length=300),
                     user: User = Depends(current_admin), db: Session = Depends(get_db)):
    """An image uploaded straight into the library (e.g. a logo or a photo already without background)."""
    data, img = await upload_png(request, file)
    fallback = (file.filename or "").rsplit(".", 1)[0]
    c = Cutout(user_id=user.id, source=None, name=clean(name, 300) or clean(fallback, 300) or "Картинка", png=data,
               width=img.size[0], height=img.size[1])
    db.add(c)
    db.commit()
    return cutout_out(c)


def get_cutout(db: Session, cid: int) -> Cutout:
    c = db.get(Cutout, cid)
    if not c:
        raise HTTPException(404, "Картинка не найдена")
    return c


@router.get("/admin/cutouts/{cid}/png")
def cutout_png(cid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return Response(get_cutout(db, cid).png, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000"})


@router.get("/admin/cutouts/{cid}/thumb")
def cutout_thumb(cid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    c = get_cutout(db, cid)
    if c.thumb is None:
        try:
            c.thumb = make_thumb(c)
        except (UnidentifiedImageError, OSError):
            raise HTTPException(404, "Картинка повреждена")
        db.commit()
    return Response(c.thumb, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000"})


class CutoutIn(BaseModel):
    name: str = Field(max_length=300)


@router.patch("/admin/cutouts/{cid}")
def rename_cutout(cid: int, data: CutoutIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    c = get_cutout(db, cid)
    c.name = clean(data.name, 300) or c.name
    db.commit()
    return cutout_out(c)


@router.delete("/admin/cutouts/{cid}", status_code=204)
def del_cutout(cid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    db.execute(delete(Cutout).where(Cutout.id == cid))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- admin: layouts ----

class LayoutsIn(BaseModel):
    card: Optional[dict[str, Any]] = None
    booklet: Optional[dict[str, Any]] = None


@router.get("/admin/print")
def get_layouts(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    s = get_setting(db, "print")
    return {k: s.get(k) for k in LAYOUT_KINDS}


@router.put("/admin/print")
def save_layouts(data: LayoutsIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    row = db.get(ShopSetting, "print") or ShopSetting(key="print", data={})
    cur = dict(row.data or {})
    for k in LAYOUT_KINDS:
        v = getattr(data, k)
        if v is not None:
            if len(repr(v)) > 200_000:
                raise HTTPException(400, "Слишком большой макет")
            cur[k] = v
    row.data = cur
    db.add(row)
    db.commit()
    return {k: cur.get(k) for k in LAYOUT_KINDS}


@router.get("/admin/print/qr.svg")
def qr_svg(text: str = Query(min_length=1, max_length=1000), color: str = Query("#2d1a33", pattern=r"^#[0-9a-fA-F]{6}$"),
           _: User = Depends(current_admin)):
    """QR code as a vector image (stays sharp when printed). No quiet zone: the layout leaves white space around it."""
    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="svg", scale=10, border=0, dark=color, light=None, xmldecl=False, svgns=True)
    return Response(out.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=86400"})
