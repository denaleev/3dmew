"""Admin → «Библиотека»: every photo and video the site keeps, in one list.

Files uploaded here live in `library_files`. Everything else is listed from where it already is (nothing is copied):
photos and cards from the card builder, neural-network cut-outs, product photos and videos, colour photos and
pictures sent by customers with requests and reviews. Other parts of the admin (the card builder, colours,
business cards and booklets, favicon) pick their pictures from this list."""
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .catalog import IMAGE_EXT, VIDEO_MIME, ext, ranged
from .config import settings
from .db import get_db
from .models import (BlobSet, CustomRequest, Cutout, FilamentColor, Item, LibraryFile, Photo, Product, ProductMedia,
                     RequestFile, Review, ReviewPhoto, User)
from .security import current_admin
from .shop import clean, jpeg

router = APIRouter(prefix="/api/admin/library")

# groups shown as filters in the library, in this order
SOURCES = {
    "upload": "Загружено в библиотеку",
    "photo": "Фото из конструктора",
    "card": "Карточки",
    "cutout": "Без фона (нейросеть)",
    "media": "Фото и видео товаров",
    "color": "Фото пластика",
    "customer": "От покупателей",
}
MAX_FILES = 30


def iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def entry(key: str, src: str, kind: str, name: str, url: str, thumb: Optional[str], size: int, t, where: str = "",
          can_delete: bool = False, mime: str = "") -> dict:
    return {"key": key, "src": src, "kind": kind, "name": name or "Без названия", "url": url, "thumb": thumb,
            "size": int(size or 0), "t": iso(t), "where": where, "del": can_delete,
            "mime": mime or ("video/mp4" if kind == "video" else "image/jpeg")}


def upload_out(f: LibraryFile) -> dict:
    url = f"/api/admin/library/files/{f.id}"
    return entry(f"up-{f.id}", "upload", f.kind, f.name, url, url + "/thumb" if f.thumb else None, f.size, f.created_at,
                 can_delete=True, mime=f.mime) | {"w": f.width, "h": f.height}


@router.get("")
def library(user: User = Depends(current_admin), db: Session = Depends(get_db)):
    out: list[dict] = []
    # uploaded straight into the library
    for f in db.execute(select(LibraryFile.id, LibraryFile.kind, LibraryFile.mime, LibraryFile.name, LibraryFile.size,
                               LibraryFile.created_at, LibraryFile.width, LibraryFile.height,
                               (LibraryFile.thumb.is_not(None)).label("has_thumb"))).all():
        url = f"/api/admin/library/files/{f.id}"
        out.append(entry(f"up-{f.id}", "upload", f.kind, f.name, url, url + "/thumb" if f.has_thumb else None, f.size,
                         f.created_at, can_delete=True, mime=f.mime) | {"w": f.width, "h": f.height})

    # photos uploaded in the card builder (the photo itself is in blobs with the same id)
    rows = db.execute(select(Photo.id, Photo.name, Photo.size, Photo.thumb, Photo.t.label("ms"), BlobSet.photo_type)
                      .join(BlobSet, BlobSet.id == Photo.id).where(Photo.user_id == user.id, BlobSet.photo.is_not(None))).all()
    for p in rows:
        out.append(entry(f"photo-{p.id}", "photo", "image", p.name, f"/api/blobs/{p.id}/photo", p.thumb, p.size,
                         _ms(p.ms), "конструктор карточек → «Фото»", mime=p.photo_type or "image/jpeg"))

    # finished cards saved in the builder's library
    mine: set[str] = set()
    rows = db.execute(select(Item.id, Item.title, Item.thumb, Item.updated_at, func.length(BlobSet.png).label("n"))
                      .join(BlobSet, BlobSet.id == Item.id)
                      .where(Item.user_id == user.id, Item.kind == "card", BlobSet.png.is_not(None))).all()
    for c in rows:
        mine.add(c.id)
        out.append(entry(f"card-{c.id}", "card", "image", c.title, f"/api/blobs/{c.id}/png", c.thumb, c.n, c.updated_at,
                         "конструктор карточек", mime="image/png"))
    # cards in the shop (made by another admin or whose builder card was deleted)
    rows = db.execute(select(Product.id, Product.title, Product.item_id, Product.updated_at,
                             func.length(Product.image).label("n")).where(Product.image.is_not(None))).all()
    for p in rows:
        if p.item_id in mine:
            continue
        out.append(entry(f"prod-{p.id}", "card", "image", p.title, f"/api/shop/products/{p.id}/image",
                         f"/api/shop/products/{p.id}/thumb", p.n, p.updated_at, "карточка товара в магазине"))

    # neural-network cut-outs (background removed)
    for c in db.execute(select(Cutout.id, Cutout.name, Cutout.source, Cutout.updated_at, Cutout.width, Cutout.height,
                               func.length(Cutout.png).label("n"))).all():
        v = int(c.updated_at.timestamp()) if c.updated_at else 0
        out.append(entry(f"cut-{c.id}", "cutout", "image", c.name, f"/api/admin/cutouts/{c.id}/png?v={v}",
                         f"/api/admin/cutouts/{c.id}/thumb?v={v}", c.n, c.updated_at,
                         "из конструктора карточек" if c.source else "загружено без фона", can_delete=True,
                         mime="image/png") | {"w": c.width, "h": c.height})

    # product photos and videos
    for m in db.execute(select(ProductMedia.id, ProductMedia.product_id, ProductMedia.kind, ProductMedia.mime,
                               ProductMedia.name, ProductMedia.size, ProductMedia.created_at, Product.title,
                               (ProductMedia.thumb.is_not(None)).label("has_thumb"))
                        .join(Product, Product.id == ProductMedia.product_id)).all():
        url = f"/api/shop/products/{m.product_id}/media/{m.id}"
        out.append(entry(f"pm-{m.id}", "media", m.kind, m.name, url, url + "/thumb" if m.has_thumb else None, m.size,
                         m.created_at, f"товар «{m.title}»", mime=m.mime))

    # photos of filament colours
    for c in db.execute(select(FilamentColor.id, FilamentColor.name, FilamentColor.updated_at,
                               func.length(FilamentColor.photo).label("n")).where(FilamentColor.photo.is_not(None))).all():
        v = int(c.updated_at.timestamp()) if c.updated_at else 0
        out.append(entry(f"col-{c.id}", "color", "image", c.name, f"/api/shop/colors/{c.id}/photo?v={v}",
                         f"/api/shop/colors/{c.id}/thumb?v={v}", c.n, c.updated_at, f"цвет «{c.name}»"))

    # pictures sent by customers: custom requests and reviews
    for x in db.execute(select(RequestFile.id, RequestFile.request_id, RequestFile.name, RequestFile.mime, RequestFile.size,
                               CustomRequest.created_at, (RequestFile.thumb.is_not(None)).label("has_thumb"))
                        .join(CustomRequest, CustomRequest.id == RequestFile.request_id)
                        .where(or_(RequestFile.mime.like("image/%"), RequestFile.mime.like("video/%")))).all():
        url = f"/api/shop/requests/{x.request_id}/files/{x.id}"
        out.append(entry(f"req-{x.id}", "customer", "video" if x.mime.startswith("video/") else "image", x.name, url,
                         url + "/thumb" if x.has_thumb else None, x.size, x.created_at, f"заявка №{x.request_id}",
                         mime=x.mime))
    for x in db.execute(select(ReviewPhoto.id, ReviewPhoto.review_id, Review.name, Review.created_at,
                               func.length(ReviewPhoto.data).label("n"))
                        .join(Review, Review.id == ReviewPhoto.review_id)).all():
        url = f"/api/shop/reviews/{x.review_id}/photos/{x.id}"
        out.append(entry(f"rev-{x.id}", "customer", "image", f"Отзыв: {x.name}", url, url + "/thumb", x.n, x.created_at,
                         f"отзыв №{x.review_id}"))

    out.sort(key=lambda e: datetime.fromisoformat(e["t"]).timestamp() if e["t"] else 0, reverse=True)
    return {"sources": SOURCES, "items": out}


def _ms(t):
    try:
        return datetime.fromtimestamp((t or 0) / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def picture(data: bytes) -> tuple[bytes, int, int]:
    """Check that the bytes are a picture; return a JPEG preview and the size."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    w, h = img.size
    return jpeg(data, 400, 82), w, h


@router.post("")
async def upload(request: Request, files: list[UploadFile] = File(...), user: User = Depends(current_admin),
                 db: Session = Depends(get_db)):
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"За раз можно до {MAX_FILES} файлов")
    added = []
    for up in files:
        name = clean(up.filename, 300) or "файл"
        e = ext(name)
        ct = up.content_type or ""
        data = await up.read()
        if e in VIDEO_MIME or ct.startswith("video/"):
            if len(data) > settings.MAX_VIDEO_MB * 1024 * 1024:
                raise HTTPException(413, f"Видео «{name}» больше {settings.MAX_VIDEO_MB} МБ")
            f = LibraryFile(user_id=user.id, kind="video", mime=VIDEO_MIME.get(e, ct or "video/mp4"), name=name,
                            size=len(data), data=data)
        elif e in IMAGE_EXT or ct.startswith("image/"):
            if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(413, f"Фото «{name}» больше {settings.MAX_UPLOAD_MB} МБ")
            try:
                thumb, w, h = picture(data)
                fmt = Image.open(io.BytesIO(data)).format or "JPEG"
            except (UnidentifiedImageError, OSError):
                raise HTTPException(400, f"Не получилось открыть «{name}» как картинку")
            mime = Image.MIME.get(fmt, ct if ct.startswith("image/") else "image/jpeg")
            f = LibraryFile(user_id=user.id, kind="image", mime=mime, name=name, size=len(data), data=data, thumb=thumb,
                            width=w, height=h)
        else:
            raise HTTPException(400, f"«{name}»: в библиотеку можно фото (JPG, PNG, WEBP) или видео (MP4, MOV, WEBM)")
        db.add(f)
        added.append(f)
    db.commit()
    return {"items": [upload_out(f) for f in added]}


def get_file(db: Session, fid: int) -> LibraryFile:
    f = db.get(LibraryFile, fid)
    if not f:
        raise HTTPException(404, "Файл не найден")
    return f


@router.get("/files/{fid}")
def file_data(fid: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    f = get_file(db, fid)
    return ranged(request, f.data, f.mime)


@router.get("/files/{fid}/thumb")
def file_thumb(fid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    f = get_file(db, fid)
    if not f.thumb:
        raise HTTPException(404, "Нет картинки")
    return Response(f.thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)


@router.patch("/files/{fid}")
def rename(fid: int, data: RenameIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    f = get_file(db, fid)
    f.name = clean(data.name, 300) or f.name
    db.commit()
    return upload_out(f)


@router.delete("/files/{fid}", status_code=204)
def remove(fid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    db.execute(delete(LibraryFile).where(LibraryFile.id == fid))
    db.commit()
    return Response(status_code=204)
