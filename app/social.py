"""Carts that are not ordered yet, favourites and reviews with moderation."""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Cart, Favorite, FilamentColor, Product, Review, ReviewPhoto, User
from .security import client_ip, current_admin, current_user, current_user_optional, is_admin, rate_limit
from .shop import clean, jpeg, notify, published_product, stamp, stats_since

public = APIRouter(prefix="/api/shop")
admin = APIRouter(prefix="/api/admin")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,40}$")


# ---------------------------------------------------------------- carts ----

class CartLine(BaseModel):
    id: int
    qty: int = Field(ge=1, le=999)
    color: int = 0


class CartIn(BaseModel):
    token: str = Field(max_length=40)
    items: list[CartLine] = Field(default_factory=list, max_length=100)
    favs: Optional[list[int]] = Field(default=None, max_length=500)  # ♡ of this browser (None = do not change)


@public.put("/cart")
def save_cart(data: CartIn, request: Request, db: Session = Depends(get_db),
              user: User | None = Depends(current_user_optional)):
    """The shop sends the cart here every time it changes, so the admin sees what is waiting in carts.
    An empty cart (or one that became an order) is removed."""
    if not TOKEN.match(data.token):
        raise HTTPException(400, "Неверный идентификатор корзины")
    rate_limit("cart:" + client_ip(request), 120, 600)
    c = db.get(Cart, data.token)
    favs = (c.favs if c else []) if data.favs is None else data.favs
    if not data.items and not favs:
        if c:
            db.delete(c)
            db.commit()
        return {"ok": True}
    ids = [i.id for i in data.items] + list(favs)
    prods = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(ids))).scalars()}
    items, total = [], Decimal(0)
    for i in data.items:
        p = prods.get(i.id)
        if p:
            items.append({"id": p.id, "qty": i.qty, "color": i.color})
            total += (p.price or 0) * i.qty
    c = c or Cart(token=data.token)
    c.items, c.total = items, total
    c.favs = [i for i in dict.fromkeys(favs) if i in prods]
    if user:
        c.user_id = user.id
    c.updated_at = datetime.now(timezone.utc)
    db.add(c)
    db.commit()
    return {"ok": True}


@admin.get("/carts")
def list_carts(days: int = 30, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    # «Сбросить статистику» also starts carts and «Отложенные» again: carts not touched since then are not counted
    # (the carts themselves stay: the buyers still see them)
    since = max(datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365))), stats_since(db))
    carts = list(db.execute(select(Cart).where(Cart.updated_at >= since).order_by(Cart.updated_at.desc())).scalars())
    pids = {i["id"] for c in carts for i in c.items or []}
    cids = {i.get("color") for c in carts for i in c.items or [] if i.get("color")}
    prods = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(pids))).scalars()} if pids else {}
    cols = {x.id: x.name for x in db.execute(select(FilamentColor).where(FilamentColor.id.in_(cids))).scalars()} if cids else {}
    users = {u.id: u for u in db.execute(select(User).where(User.id.in_({c.user_id for c in carts if c.user_id}))).scalars()}
    out = []
    for c in carts:
        lines = []
        for i in c.items or []:
            p = prods.get(i["id"])
            if p:
                lines.append({"product_id": p.id, "title": p.title, "qty": i["qty"], "price": float(p.price),
                              "color": cols.get(i.get("color"), ""), "thumb": f"/api/shop/products/{p.id}/thumb?v={stamp(p.updated_at)}"})
        if not lines:
            continue
        u = users.get(c.user_id)
        out.append({"token": c.token[:8], "id": c.token, "user": {"name": u.name, "login": u.login} if u else None,
                    "items": lines, "pieces": sum(x["qty"] for x in lines),
                    "total": round(sum(x["price"] * x["qty"] for x in lines), 2),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None})
    # what is put in carts most often
    top: dict[int, dict] = {}
    for c in out:
        for x in c["items"]:
            e = top.setdefault(x["product_id"], {"product_id": x["product_id"], "title": x["title"], "carts": 0, "qty": 0})
            e["carts"] += 1
            e["qty"] += x["qty"]
    # «Отложенные»: what visitors marked with ♡
    fav_rows = [c for c in carts if c.favs]
    fids = {i for c in fav_rows for i in c.favs}
    fprods = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(fids))).scalars()} if fids else {}
    per: dict[int, dict] = {}
    people = []
    for c in fav_rows:
        u = users.get(c.user_id)
        lst = []
        cart_ids = {i.get("id") for i in c.items or []}
        for i in c.favs:
            p = fprods.get(i)
            if not p:
                continue
            lst.append({"product_id": p.id, "title": p.title, "price": float(p.price),
                        "thumb": f"/api/shop/products/{p.id}/thumb?v={stamp(p.updated_at)}"})
            e = per.setdefault(p.id, {"product_id": p.id, "title": p.title, "price": float(p.price), "people": 0,
                                      "in_cart": 0})
            e["people"] += 1
            e["in_cart"] += p.id in cart_ids  # marked and also put in the cart
        if lst:
            people.append({"id": c.token, "user": {"name": u.name, "login": u.login} if u else None, "items": lst,
                           "updated_at": c.updated_at.isoformat() if c.updated_at else None})
    fav_top = sorted(per.values(), key=lambda e: -e["people"])
    return {"items": out, "top": sorted(top.values(), key=lambda e: (-e["carts"], -e["qty"]))[:10],
            "total": round(sum(c["total"] for c in out), 2),
            "favs": {"people": len(people), "marks": sum(e["people"] for e in fav_top), "products": len(fav_top),
                     "value": round(sum(e["price"] * e["people"] for e in fav_top), 2), "top": fav_top, "list": people}}


@admin.delete("/carts/{token}", status_code=204)
def delete_cart(token: str, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    db.execute(delete(Cart).where(Cart.token == token))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- favourites ----
# guests keep favourites in the browser; signed-in buyers also on the server, so they see them on every device

@public.get("/favorites")
def favorites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"ids": list(db.execute(select(Favorite.product_id).where(Favorite.user_id == user.id)
                                   .order_by(Favorite.created_at.desc())).scalars())}


class FavIn(BaseModel):
    ids: list[int] = Field(max_length=500)


@public.post("/favorites")
def add_favorites(data: FavIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Adds products (also the ones collected before signing in)."""
    have = set(db.execute(select(Favorite.product_id).where(Favorite.user_id == user.id)).scalars())
    real = set(db.execute(select(Product.id).where(Product.id.in_(data.ids))).scalars())
    for pid in dict.fromkeys(data.ids):
        if pid in real and pid not in have:
            db.add(Favorite(user_id=user.id, product_id=pid))
    db.commit()
    return favorites(user, db)


@public.delete("/favorites/{pid}")
def remove_favorite(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == pid))
    db.commit()
    return favorites(user, db)


# ---------------------------------------------------------------- reviews ----

def ratings(db: Session, pids=None) -> dict[int, tuple[float, int]]:
    st = select(Review.product_id, func.avg(Review.rating), func.count()).where(Review.status == "approved")
    if pids is not None:
        st = st.where(Review.product_id.in_(list(pids)))
    return {pid: (round(float(a), 1), int(n)) for pid, a, n in db.execute(st.group_by(Review.product_id)).all()}


def photo_ids(db: Session, rids) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    if rids:
        for pid, rid in db.execute(select(ReviewPhoto.id, ReviewPhoto.review_id).where(ReviewPhoto.review_id.in_(list(rids)))
                                   .order_by(ReviewPhoto.id)).all():
            out.setdefault(rid, []).append(pid)
    return out


def review_out(r: Review, photos: list[int], admin_view: bool = False, title: str = "") -> dict:
    o = {"id": r.id, "name": r.name, "rating": r.rating, "text": r.text,
         "created_at": r.created_at.isoformat() if r.created_at else None,
         "photos": [{"url": f"/api/shop/reviews/{r.id}/photos/{i}", "thumb": f"/api/shop/reviews/{r.id}/photos/{i}/thumb"}
                    for i in photos]}
    if admin_view:
        o.update(status=r.status, product_id=r.product_id, product_title=title, user_id=r.user_id)
    return o


@public.get("/products/{pid}/reviews")
def product_reviews(pid: int, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    published_product(db, pid, user)
    rows = list(db.execute(select(Review).where(Review.product_id == pid, Review.status == "approved")
                           .order_by(Review.created_at.desc())).scalars())
    ph = photo_ids(db, [r.id for r in rows])
    avg, n = ratings(db, [pid]).get(pid, (0, 0))
    stars = {k: 0 for k in range(1, 6)}
    for r in rows:
        stars[r.rating] = stars.get(r.rating, 0) + 1
    return {"rating": avg, "count": n, "stars": stars, "items": [review_out(r, ph.get(r.id, [])) for r in rows]}


@public.post("/products/{pid}/reviews")
async def add_review(pid: int, request: Request, name: str = Form(..., max_length=80), rating: int = Form(...),
                     text: str = Form("", max_length=3000), consent: str = Form(""),
                     photos: list[UploadFile] = File(default=[]), db: Session = Depends(get_db),
                     user: User | None = Depends(current_user_optional)):
    p = published_product(db, pid, user)
    rate_limit("review:" + client_ip(request), 5, 3600)
    if consent not in ("1", "true", "on"):
        raise HTTPException(400, "Нужно согласие на публикацию отзыва")
    if not 1 <= rating <= 5:
        raise HTTPException(400, "Поставь оценку от 1 до 5 звёзд")
    name = clean(name, 80)
    if not name:
        raise HTTPException(400, "Укажи имя")
    photos = [f for f in photos if f and f.filename][:3]
    r = Review(product_id=p.id, user_id=user.id if user else None, name=name, rating=rating, text=clean(text, 3000),
               status="pending")
    db.add(r)
    db.flush()
    for f in photos:
        data = await f.read()
        if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, "Фото слишком большое")
        try:
            db.add(ReviewPhoto(review_id=r.id, data=jpeg(data, 1600, 86), thumb=jpeg(data, 300, 80)))
        except Exception:  # noqa: BLE001
            raise HTTPException(400, f"«{f.filename}» — не картинка")
    db.commit()
    notify(f"⭐ Новый отзыв на «{p.title}»: {'★' * rating} от {name}. Проверь в админке → Отзывы")
    return {"ok": True, "id": r.id}


@public.get("/reviews/{rid}/photos/{phid}")
@public.get("/reviews/{rid}/photos/{phid}/{kind}")
def review_photo(rid: int, phid: int, kind: str = "image", db: Session = Depends(get_db),
                 user: User | None = Depends(current_user_optional)):
    r = db.get(Review, rid)
    ph = db.get(ReviewPhoto, phid)
    if not r or not ph or ph.review_id != rid or (r.status != "approved" and not is_admin(user)):
        raise HTTPException(404, "Не найдено")
    return Response(ph.thumb if kind == "thumb" else ph.data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@admin.get("/reviews")
def admin_reviews(status: str = "pending", db: Session = Depends(get_db), _: User = Depends(current_admin)):
    st = select(Review).order_by(Review.created_at.desc()).limit(300)
    if status != "all":
        st = st.where(Review.status == status)
    rows = list(db.execute(st).scalars())
    ph = photo_ids(db, [r.id for r in rows])
    titles = dict(db.execute(select(Product.id, Product.title).where(Product.id.in_({r.product_id for r in rows}))).all()) if rows else {}
    counts = dict(db.execute(select(Review.status, func.count()).group_by(Review.status)).all())
    return {"items": [review_out(r, ph.get(r.id, []), True, titles.get(r.product_id, "")) for r in rows], "counts": counts}


class ReviewPatch(BaseModel):
    status: str = Field(pattern="^(pending|approved|rejected)$")


@admin.patch("/reviews/{rid}")
def moderate_review(rid: int, data: ReviewPatch, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    r = db.get(Review, rid)
    if not r:
        raise HTTPException(404, "Отзыв не найден")
    r.status = data.status
    db.commit()
    return {"ok": True}


@admin.delete("/reviews/{rid}", status_code=204)
def delete_review(rid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    r = db.get(Review, rid)
    if r:
        db.delete(r)
        db.commit()
    return Response(status_code=204)
