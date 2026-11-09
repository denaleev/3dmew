"""Library, drafts, photos, images and settings of the signed-in user (all in PostgreSQL)."""
from typing import Annotated, Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import BlobSet, Item, ItemFile, Photo, Pref, User
from .security import current_user, is_admin

router = APIRouter(prefix="/api")
ID = r"^[A-Za-z0-9_-]{1,40}$"


class ItemIn(BaseModel):
    kind: str = Field(pattern="^(card|draft)$")
    title: str = Field(default="", max_length=300)
    thumb: Optional[str] = Field(default=None, max_length=2_000_000)
    state: Optional[dict[str, Any]] = None
    t: int


class PhotoIn(BaseModel):
    name: str = Field(default="фото", max_length=300)
    size: int = 0
    thumb: Optional[str] = Field(default=None, max_length=2_000_000)
    t: int


def own(db: Session, model, id_: str, user: User):
    row = db.get(model, id_)
    if row is not None and row.user_id != user.id:
        raise HTTPException(404, "Не найдено")
    return row


def item_out(i: Item, full: bool = True) -> dict:
    o = {"id": i.id, "kind": i.kind, "title": i.title, "thumb": i.thumb, "t": i.t}
    if full:
        o["state"] = i.state or {}
    return o


@router.get("/items")
def list_items(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Item).where(Item.user_id == user.id).order_by(Item.t.desc())).scalars()
    nfiles = dict(db.execute(select(ItemFile.item_id, func.count()).where(ItemFile.user_id == user.id).group_by(ItemFile.item_id)).all())
    return [item_out(i, full=False) | {"files": nfiles.get(i.id, 0)} for i in rows]


@router.get("/items/{item_id}")
def get_item(item_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    i = own(db, Item, item_id, user)
    if not i:
        raise HTTPException(404, "Не найдено")
    return item_out(i)


@router.put("/items/{item_id}")
def put_item(data: ItemIn, item_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    i = own(db, Item, item_id, user) or Item(id=item_id, user_id=user.id)
    i.kind, i.title, i.thumb, i.state, i.t = data.kind, data.title, data.thumb, data.state, data.t
    db.add(i)
    db.commit()
    return {"ok": True}


@router.delete("/items/{item_id}", status_code=204)
def del_item(item_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Item).where(Item.id == item_id, Item.user_id == user.id))
    db.commit()
    return Response(status_code=204)


@router.get("/photos")
def list_photos(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Photo).where(Photo.user_id == user.id).order_by(Photo.t.desc())).scalars()
    return [{"id": p.id, "name": p.name, "size": p.size, "thumb": p.thumb, "t": p.t} for p in rows]


@router.get("/photos/{photo_id}")
def get_photo(photo_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own(db, Photo, photo_id, user)
    if not p:
        raise HTTPException(404, "Не найдено")
    return {"id": p.id, "name": p.name, "size": p.size, "thumb": p.thumb, "t": p.t}


@router.put("/photos/{photo_id}")
def put_photo(photo_id: Annotated[str, Path(pattern=ID)], data: PhotoIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own(db, Photo, photo_id, user) or Photo(id=photo_id, user_id=user.id)
    p.name, p.size, p.thumb, p.t = data.name, data.size, data.thumb, data.t
    db.add(p)
    db.commit()
    return {"ok": True}


@router.delete("/photos/{photo_id}", status_code=204)
def del_photo(photo_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Photo).where(Photo.id == photo_id, Photo.user_id == user.id))
    db.commit()
    return Response(status_code=204)


BLOB_FIELDS = ("png", "photo", "product", "manual")
TYPES = {"png": "image/png", "product": "image/png", "manual": "application/octet-stream"}


@router.get("/blobs/{blob_id}")
def blob_meta(blob_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = own(db, BlobSet, blob_id, user)
    if not b:
        raise HTTPException(404, "Не найдено")
    return {"id": b.id, "productCut": b.product_cut, "has": {f: getattr(b, f) is not None for f in BLOB_FIELDS}}


@router.get("/blobs/{blob_id}/{field}")
def blob_data(blob_id: Annotated[str, Path(pattern=ID)], field: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if field not in BLOB_FIELDS:
        raise HTTPException(404, "Не найдено")
    b = own(db, BlobSet, blob_id, user)
    data = getattr(b, field) if b else None
    if data is None:
        raise HTTPException(404, "Не найдено")
    mt = b.photo_type if field == "photo" else TYPES[field]
    return Response(content=data, media_type=mt or "application/octet-stream", headers={"Cache-Control": "private, max-age=0"})


@router.put("/blobs/{blob_id}")
async def put_blob(blob_id: Annotated[str, Path(pattern=ID)], request: Request, product_cut: str = Form("1"),
                   png: UploadFile | None = File(None), photo: UploadFile | None = File(None),
                   product: UploadFile | None = File(None), manual: UploadFile | None = File(None),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(413, f"Слишком большой файл (больше {settings.MAX_UPLOAD_MB} МБ)")
    b = own(db, BlobSet, blob_id, user) or BlobSet(id=blob_id, user_id=user.id)
    for name, up in (("png", png), ("photo", photo), ("product", product), ("manual", manual)):
        setattr(b, name, await up.read() if up else None)
    if photo:
        ct = photo.content_type or ""
        b.photo_type = ct if ct.startswith("image/") else "image/jpeg"
    b.product_cut = product_cut != "0"
    db.add(b)
    db.commit()
    return {"ok": True}


@router.delete("/blobs/{blob_id}", status_code=204)
def del_blob(blob_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(BlobSet).where(BlobSet.id == blob_id, BlobSet.user_id == user.id))
    db.commit()
    return Response(status_code=204)


@router.get("/prefs")
def get_prefs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Pref, user.id)
    return (p.data if p else None) or {}


@router.put("/prefs")
def put_prefs(data: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    themes = data.get("themes")
    if themes is not None and (not isinstance(themes, list) or len(themes) > 100):
        raise HTTPException(400, "Неверные цвета")
    p = db.get(Pref, user.id) or Pref(user_id=user.id, data={})
    p.data = {**(p.data or {}), **data}
    db.add(p)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- print files of a card ----
MODEL_EXT = (".3mf", ".stl", ".obj", ".step", ".stp", ".gcode", ".bgcode", ".gco", ".zip")


def file_out(f: ItemFile) -> dict:
    return {"id": f.id, "name": f.name, "size": f.size, "note": f.note, "t": int(f.created_at.timestamp() * 1000) if f.created_at else 0,
            "url": f"/api/items/{f.item_id}/files/{f.id}"}


def list_item_files(db: Session, item_id: str) -> list[dict]:
    rows = db.execute(select(ItemFile.id, ItemFile.item_id, ItemFile.name, ItemFile.size, ItemFile.note, ItemFile.created_at)
                      .where(ItemFile.item_id == item_id).order_by(ItemFile.id)).all()
    return [file_out(r) for r in rows]


@router.get("/items/{item_id}/files")
def item_files(item_id: Annotated[str, Path(pattern=ID)], user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not own(db, Item, item_id, user):
        return []
    return list_item_files(db, item_id)


@router.post("/items/{item_id}/files")
async def add_item_file(item_id: Annotated[str, Path(pattern=ID)], request: Request, file: UploadFile = File(...),
                        note: str = Form("", max_length=300), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if int(request.headers.get("content-length") or 0) > settings.MAX_MODEL_MB * 1024 * 1024:
        raise HTTPException(413, f"Файл больше {settings.MAX_MODEL_MB} МБ")
    it = own(db, Item, item_id, user)
    if not it:
        raise HTTPException(404, "Сначала сохрани карточку в библиотеку")
    name = (file.filename or "model.3mf").replace("\\", "/").split("/")[-1][:300]
    if not name.lower().endswith(MODEL_EXT):
        raise HTTPException(400, "Можно файлы 3MF, STL, OBJ, STEP, G-code или ZIP")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    f = ItemFile(item_id=it.id, user_id=user.id, name=name, size=len(data), note=note.strip()[:300], data=data)
    db.add(f)
    db.commit()
    return file_out(f)


@router.get("/items/{item_id}/files/{file_id}")
def get_item_file(item_id: Annotated[str, Path(pattern=ID)], file_id: int, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    f = db.get(ItemFile, file_id)
    if not f or f.item_id != item_id or (f.user_id != user.id and not is_admin(user)):
        raise HTTPException(404, "Файл не найден")
    return download(f)


def download(f: ItemFile) -> Response:
    ascii_name = "".join(c if c.isascii() and (c.isalnum() or c in "._- ") else "_" for c in f.name)
    return Response(f.data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(f.name)}",
        "Cache-Control": "private, max-age=0"})


@router.delete("/items/{item_id}/files/{file_id}", status_code=204)
def del_item_file(item_id: Annotated[str, Path(pattern=ID)], file_id: int, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    db.execute(delete(ItemFile).where(ItemFile.id == file_id, ItemFile.item_id == item_id, ItemFile.user_id == user.id))
    db.commit()
    return Response(status_code=204)
