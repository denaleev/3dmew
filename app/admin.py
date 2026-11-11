"""Shop management: publishing cards, orders and their history, custom requests, statistics, settings."""
import base64
import csv
import io
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import pricing
from .db import get_db
from .models import (ORDER_STATUSES, REQUEST_STATUSES, BlobSet, CustomRequest, FilamentColor, Item, ItemFile, Order, OrderItem, Product,
                     ShopSetting, User)
from .security import current_admin
from .store import list_item_files
from .shop import (DELIVERY, ORDER_LABELS, REQUEST_LABELS, SHOP_DEFAULTS, LONG_TEXT, PAGE_TEXT, add_event, calc_settings, clean, f,
                   get_setting, jpeg, load_order, load_request, order_events, order_lines, order_out, product_out,
                   request_events, request_files, request_out, return_stock, shop_info, sold_counts, stamp, tile_from_card,
                   stats_since)

router = APIRouter(prefix="/api/admin")
OPEN = ("new", "confirmed", "printing")  # still need the printer
CLOSED = ("done", "cancelled")


# ---------------------------------------------------------------- settings ----

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return {"calc": calc_settings(db), "shop": shop_info(db), "delivery_all": DELIVERY,
            "calc_defaults": pricing.merge_settings({})}


class SettingsIn(BaseModel):
    calc: Optional[dict[str, Any]] = None
    shop: Optional[dict[str, Any]] = None


def put_setting(db: Session, key: str, data: dict) -> None:
    row = db.get(ShopSetting, key) or ShopSetting(key=key, data={})
    row.data = data
    db.add(row)


@router.put("/settings")
def save_settings(data: SettingsIn, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    if data.calc is not None:
        put_setting(db, "calc", pricing.merge_settings(data.calc))
    if data.shop is not None:
        cur = shop_info(db)
        for k, v in data.shop.items():
            if k == "delivery" and isinstance(v, list):
                cur[k] = [d for d in v if d in DELIVERY] or ["pickup"]
            elif k == "min_order":
                cur[k] = pricing._num(v, 0)
            elif k == "max_link":  # the «Мы в MAX» button: only a web link
                v = clean(str(v), 300)
                cur[k] = v if v.startswith(("https://", "http://")) else ""
            elif k in SHOP_DEFAULTS:
                cur[k] = clean(str(v), 20000 if k in PAGE_TEXT else 8000 if k in LONG_TEXT else 300)
        put_setting(db, "shop", cur)
    db.commit()
    return get_settings(db, _)


# ---------------------------------------------------------------- products ----

def num(v, default=0.0) -> float:
    return pricing._num(v, default)


def state_calc(st: dict) -> dict:
    """Calculator fields of the builder → calculator input."""
    return {"material": st.get("calcMat") if st.get("calcMat") not in (None, "", "__other") else "PLA",
            "kg_price": num(st.get("calcKg")), "grams": num(st.get("calcGrams")), "hours": num(st.get("calcH")),
            "minutes": num(st.get("calcM")), "pieces": int(num(st.get("calcN"), 1) or 1),
            "finish_min": num(st.get("calcFinish")), "extras": num(st.get("calcExtra")),
            "markup_pct": st.get("calcMarkup") if str(st.get("calcMarkup") or "").strip() else None}


@router.post("/products/from-item/{item_id}")
def publish_card(item_id: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Publish (or update) a card from the builder library in the shop."""
    it = db.get(Item, item_id)
    if not it or it.user_id != admin.id or it.kind != "card":
        raise HTTPException(404, "Сначала сохрани карточку в библиотеку")
    st = it.state or {}
    price = num(st.get("price"))
    if price <= 0:
        raise HTTPException(400, "Укажи цену товара (вкладка «Текст» или калькулятор)")
    p = db.execute(select(Product).where(Product.item_id == it.id)).scalar_one_or_none()
    new = p is None
    if new:
        p = Product(item_id=it.id, published=True, stock=0, sort=0, views=0)
    p.title = (st.get("title") or it.title or "Без названия").strip()[:300]
    p.description = (st.get("desc") or "").strip()[:5000]
    p.features = (st.get("feats") or "").strip()[:5000]
    if "shopNote" in st:  # «Примечание» from the builder's «Витрина» block
        p.note = str(st.get("shopNote") or "").strip()[:3000]
    p.category = (st.get("shopCat") or "").strip()[:80]
    if str(st.get("shopStock") or "").strip():
        p.stock = max(0, int(num(st.get("shopStock"))))
    p.price = Decimal(str(round(price, 2)))
    old = num(st.get("old"))
    p.old_price = Decimal(str(round(old, 2))) if old > price else None
    cin = state_calc(st)
    if cin["grams"] or cin["hours"] or cin["minutes"]:
        res = pricing.calc(cin, get_setting(db, "calc"))
        p.calc = {"input": cin, "result": res}
        p.cost, p.print_minutes, p.grams, p.material = Decimal(str(res["cost"])), res["print_minutes"], res["grams"], cin["material"]
    elif new:
        p.calc, p.cost, p.print_minutes, p.grams, p.material = None, None, 0, 0, ""
    # no calculator in the builder: keep the weight and print time already set for the product (e.g. in «✏️ Изменить»)
    b = db.get(BlobSet, it.id)
    src = b.png if b and b.png else None
    if src is None and it.thumb and it.thumb.startswith("data:image"):
        src = base64.b64decode(it.thumb.split(",", 1)[1])
    if src is None:
        raise HTTPException(400, "У карточки нет картинки: открой её и сохрани ещё раз")
    p.image, p.thumb = jpeg(src, 1600, 88), jpeg(src, 520, 82)
    # colours a buyer can choose, ticked in the builder («Витрина: цвета, фото и видео»); empty = the whole palette
    if "shopColors" in st:
        want = [int(x) for x in str(st.get("shopColors") or "").split(",") if x.strip().isdigit()]
        known = set(db.execute(select(FilamentColor.id).where(FilamentColor.id.in_(want))).scalars()) if want else set()
        p.colors = [c for c in dict.fromkeys(want) if c in known] or None
    # the plastic colour typed in the builder's calculator becomes the standard colour, if it is in the palette
    cname = str(st.get("calcColor") or "").strip().lower()
    if cname:
        m = next((c for c in db.execute(select(FilamentColor)).scalars() if c.name.strip().lower() == cname), None)
        p.default_color = m.id if m else None
    # catalogue preview without the price plate; the builder sends a cleaner one right after publishing
    p.tile = tile_from_card(src, str((it.state or {}).get("layout") or ""))
    db.add(p)
    db.commit()
    return {"id": p.id, "new": new, "cost": f(p.cost), "print_minutes": p.print_minutes, "url": f"/#product/{p.id}"}


@router.get("/products/by-item/{item_id}")
def product_by_item(item_id: str, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """The shop product made from a builder card (to show «Сохранить изменения» and fill in the weight)."""
    p = db.execute(select(Product).where(Product.item_id == item_id)).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Карточка ещё не опубликована")
    return {"id": p.id, "grams": f(p.grams), "print_minutes": p.print_minutes, "colors": list(p.colors or []),
            "published": p.published, "url": f"/#product/{p.id}"}


@router.get("/products")
def list_products(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    sold = sold_counts(db)
    rev = dict(db.execute(select(OrderItem.product_id, func.sum(OrderItem.price * OrderItem.qty))
                          .join(Order, Order.id == OrderItem.order_id).where(Order.status != "cancelled")
                          .group_by(OrderItem.product_id)).all())
    rows = db.execute(select(Product).order_by(Product.sort, Product.id.desc())).scalars()
    nfiles = dict(db.execute(select(ItemFile.item_id, func.count()).group_by(ItemFile.item_id)).all())
    return [product_out(p, full=False, sold=sold.get(p.id, 0)) | {
        "published": p.published, "sort": p.sort, "views": p.views, "cost": f(p.cost), "grams": f(p.grams),
        "revenue": f(rev.get(p.id) or 0), "item_id": p.item_id, "calc": p.calc,
        "description": p.description, "files": nfiles.get(p.item_id, 0)} for p in rows]


class ProductPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    category: Optional[str] = Field(default=None, max_length=80)
    price: Optional[float] = Field(default=None, gt=0)
    old_price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0, le=100000)
    published: Optional[bool] = None
    sort: Optional[int] = Field(default=None, ge=-100000, le=100000)
    features: Optional[str] = Field(default=None, max_length=5000)
    note: Optional[str] = Field(default=None, max_length=3000)
    colors: Optional[list[int]] = Field(default=None, max_length=200)
    grams: Optional[float] = Field(default=None, ge=0, le=100000)
    default_color: Optional[int] = Field(default=None, ge=0)


@router.patch("/products/{pid}")
def patch_product(pid: int, data: ProductPatch, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Товар не найден")
    for k, v in data.model_dump(exclude_unset=True).items():
        if k in ("price", "old_price") and v is not None:
            v = Decimal(str(round(v, 2))) if v > 0 else None
        if k in ("title", "description", "category", "features", "note") and v is not None:
            v = v.strip()
        if k == "colors" and v is not None:
            known = set(db.execute(select(FilamentColor.id).where(FilamentColor.id.in_(v))).scalars())
            v = [c for c in dict.fromkeys(v) if c in known] or None
        if k == "default_color":
            v = v if v and db.get(FilamentColor, v) else None
        if k == "title" and not v:
            raise HTTPException(400, "Нужно название")
        setattr(p, k, v)
    if p.price is None:
        raise HTTPException(400, "Нужна цена")
    db.commit()
    return {"ok": True}


class ProductNew(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    price: float = Field(gt=0)
    category: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=5000)
    features: str = Field(default="", max_length=5000)
    stock: int = Field(default=0, ge=0, le=100000)
    published: bool = False


@router.post("/products")
def create_product(data: ProductNew, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """A product without a builder card: photos are added afterwards."""
    p = Product(title=data.title.strip(), price=Decimal(str(round(data.price, 2))), category=data.category.strip(),
                description=data.description.strip(), features=data.features.strip(), stock=data.stock,
                published=data.published, sort=0, views=0, print_minutes=0, grams=0, material="")
    db.add(p)
    db.commit()
    return {"id": p.id, "url": f"/#product/{p.id}"}


@router.delete("/products/{pid}", status_code=204)
def delete_product(pid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    p = db.get(Product, pid)
    if p:
        db.delete(p)
        db.commit()
    return Response(status_code=204)


@router.get("/published")
def published_map(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """Which library cards are already in the shop (for the builder)."""
    return {iid: {"id": pid, "published": pub} for iid, pid, pub in
            db.execute(select(Product.item_id, Product.id, Product.published).where(Product.item_id.is_not(None))).all()}


# ---------------------------------------------------------------- orders ----

@router.get("/orders")
def list_orders(status: str = "", q: str = "", days: int = Query(0, ge=0, le=3650), limit: int = Query(300, le=2000),
                db: Session = Depends(get_db), _: User = Depends(current_admin)):
    st = select(Order)
    if status == "open":
        st = st.where(Order.status.not_in(CLOSED))
    elif status:
        st = st.where(Order.status == status)
    if days:
        st = st.where(Order.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    if q.strip():
        like = f"%{q.strip()[:80]}%"
        conds = [Order.name.ilike(like), Order.phone.ilike(like), Order.email.ilike(like), Order.address.ilike(like)]
        if q.strip().lstrip("№#").isdigit():
            conds.append(Order.id == int(q.strip().lstrip("№#")))
        st = st.where(or_(*conds))
    rows = list(db.execute(st.order_by(Order.id.desc()).limit(limit)).scalars())
    lines = defaultdict(list)
    if rows:
        for i in db.execute(select(OrderItem).where(OrderItem.order_id.in_([o.id for o in rows])).order_by(OrderItem.id)).scalars():
            lines[i.order_id].append(i)
    counts = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    return {"items": [order_out(o, lines[o.id], admin=True) for o in rows], "counts": counts, "labels": ORDER_LABELS}


@router.get("/orders/{oid}")
def admin_order(oid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    o = load_order(db, oid)
    out = order_out(o, order_lines(db, o.id), order_events(db, o.id), admin=True)
    for line in out["items"]:  # print files kept with the card: 3MF etc.
        p = db.get(Product, line["product_id"]) if line["product_id"] else None
        line["files"] = list_item_files(db, p.item_id) if p and p.item_id else []
    return out


class OrderPatch(BaseModel):
    status: Optional[str] = None
    admin_note: Optional[str] = Field(default=None, max_length=5000)
    paid: Optional[bool] = None
    due_date: Optional[str] = Field(default=None, max_length=20)
    comment: Optional[str] = Field(default=None, max_length=2000)  # a message in the history, visible to the customer


@router.patch("/orders/{oid}")
def patch_order(oid: int, data: OrderPatch, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    o = load_order(db, oid)
    changed = []
    if data.status and data.status != o.status:
        if data.status not in ORDER_STATUSES:
            raise HTTPException(400, "Неизвестный статус")
        if data.status == "cancelled":
            return_stock(db, o)
        o.status = data.status
        o.closed_at = datetime.now(timezone.utc) if data.status in CLOSED else None
        add_event(db, order_id=o.id, who_=admin.name, status=data.status, text=clean(data.comment, 2000))
        data.comment = None
    if data.paid is not None and data.paid != o.paid:
        o.paid = data.paid
        changed.append("оплачен" if data.paid else "оплата снята")
    if data.due_date is not None:
        try:
            o.due_date = datetime.fromisoformat(data.due_date).replace(tzinfo=timezone.utc) if data.due_date else None
        except ValueError:
            raise HTTPException(400, "Дата в формате ГГГГ-ММ-ДД")
        changed.append(f"срок: {data.due_date or 'не задан'}")
    if data.admin_note is not None and data.admin_note != o.admin_note:
        o.admin_note = data.admin_note
        changed.append("заметка")
    if changed:
        add_event(db, order_id=o.id, who_=admin.name, text="🔒 " + ", ".join(changed))
    if data.comment:
        add_event(db, order_id=o.id, who_=admin.name, text=clean(data.comment, 2000))
    db.commit()
    return admin_order(oid, db, admin)


class ItemPrice(BaseModel):
    price: float = Field(gt=0, le=10_000_000)  # for one piece
    cost: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    print_minutes: Optional[int] = Field(default=None, ge=0, le=100000)
    grams: Optional[float] = Field(default=None, ge=0, le=100000)


@router.patch("/orders/{oid}/items/{iid}")
def set_item_price(oid: int, iid: int, data: ItemPrice, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Final price of a line (e.g. several colours, after the slicer). The order total is recounted."""
    o = load_order(db, oid)
    it = db.get(OrderItem, iid)
    if not it or it.order_id != o.id:
        raise HTTPException(404, "Позиция не найдена")
    it.price = Decimal(str(round(data.price, 2)))
    if data.cost is not None:
        it.cost = Decimal(str(round(data.cost, 2)))
    if data.print_minutes is not None:
        it.print_minutes = data.print_minutes
    if data.grams is not None:
        it.grams = Decimal(str(round(data.grams, 1)))
    it.price_pending = False
    items = list(db.execute(select(OrderItem).where(OrderItem.order_id == o.id)).scalars())
    o.total = sum((i.price * i.qty for i in items), Decimal(0))
    o.cost = sum(((i.cost or 0) * i.qty for i in items), Decimal(0))
    o.print_minutes = sum((i.print_minutes or 0) * (i.qty - (i.from_stock or 0)) for i in items)
    o.grams = sum(((i.grams or 0) * (i.qty - (i.from_stock or 0)) for i in items), Decimal(0))
    add_event(db, order_id=o.id, who_=admin.name,
              text=f"Цена за «{it.title}»{' (' + it.color + ')' if it.color else ''} подтверждена: {f(it.price):.0f} ₽ за шт. "
                   f"Итого по заказу: {f(o.total):.0f} ₽")
    db.commit()
    return admin_order(oid, db, admin)


@router.get("/orders.csv")
def orders_csv(days: int = Query(0, ge=0, le=3650), db: Session = Depends(get_db), _: User = Depends(current_admin)):
    st = select(Order).order_by(Order.id)
    if days:
        st = st.where(Order.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["№", "Дата", "Статус", "Имя", "Телефон", "Почта", "Доставка", "Адрес", "Товары", "Сумма", "Себестоимость",
                "Прибыль", "Печать, ч", "Пластик, г", "Оплачен", "Срок", "Закрыт"])
    for o in db.execute(st).scalars():
        items = ", ".join(f"{i.title}{' (' + i.color + ')' if i.color else ''} × {i.qty}" for i in order_lines(db, o.id))
        w.writerow([o.id, o.created_at.strftime("%d.%m.%Y %H:%M"), ORDER_LABELS.get(o.status, o.status), o.name, o.phone,
                    o.email, DELIVERY.get(o.delivery, o.delivery), o.address, items, f"{o.total:.2f}".replace(".", ","),
                    f"{o.cost:.2f}".replace(".", ","), f"{o.total - o.cost:.2f}".replace(".", ","),
                    f"{o.print_minutes / 60:.1f}".replace(".", ","), f"{o.grams:.0f}", "да" if o.paid else "нет",
                    o.due_date.date().isoformat() if o.due_date else "",
                    o.closed_at.strftime("%d.%m.%Y") if o.closed_at else ""])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="orders.csv"'})


# ---------------------------------------------------------------- requests ----

@router.get("/requests")
def list_requests(status: str = "", db: Session = Depends(get_db), _: User = Depends(current_admin)):
    st = select(CustomRequest)
    if status == "open":
        st = st.where(CustomRequest.status.in_(("new", "reviewing", "quoted", "accepted")))
    elif status:
        st = st.where(CustomRequest.status == status)
    rows = db.execute(st.order_by(CustomRequest.id.desc()).limit(500)).scalars()
    counts = dict(db.execute(select(CustomRequest.status, func.count()).group_by(CustomRequest.status)).all())
    return {"items": [request_out(r, request_files(db, r.id), admin=True) for r in rows], "counts": counts,
            "labels": REQUEST_LABELS}


@router.get("/requests/{rid}")
def admin_request(rid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    r = load_request(db, rid)
    return request_out(r, request_files(db, r.id), request_events(db, r.id), admin=True)


class RequestPatch(BaseModel):
    status: Optional[str] = None
    quote_price: Optional[float] = Field(default=None, ge=0)
    quote_cost: Optional[float] = Field(default=None, ge=0)
    quote_minutes: Optional[int] = Field(default=None, ge=0)
    quote_grams: Optional[float] = Field(default=None, ge=0)
    quote_text: Optional[str] = Field(default=None, max_length=5000)
    admin_note: Optional[str] = Field(default=None, max_length=5000)


@router.patch("/requests/{rid}")
def patch_request(rid: int, data: RequestPatch, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    r = load_request(db, rid)
    d = data.model_dump(exclude_unset=True)
    for k in ("quote_price", "quote_cost", "quote_grams"):
        if k in d:
            setattr(r, k, Decimal(str(round(d[k], 2))) if d[k] else None)
    for k in ("quote_minutes", "quote_text", "admin_note"):
        if k in d:
            setattr(r, k, d[k] if d[k] is not None else ("" if k != "quote_minutes" else None))
    st = d.get("status")
    if st and st != r.status:
        if st not in REQUEST_STATUSES or st == "ordered":
            raise HTTPException(400, "Неизвестный статус")
        if st == "quoted" and not r.quote_price:
            raise HTTPException(400, "Сначала укажи цену")
        r.status = st
        text = r.quote_text if st == "quoted" else ""
        if st == "quoted":
            text = f"Цена: {r.quote_price:.0f} ₽" + (f", печать ≈ {r.quote_minutes / 60:.1f} ч" if r.quote_minutes else "") + (f". {r.quote_text}" if r.quote_text else "")
        add_event(db, request_id=r.id, who_=admin.name, status=st, text=text)
    elif d.keys() - {"admin_note"}:
        add_event(db, request_id=r.id, who_=admin.name, text="изменена оценка")
    db.commit()
    return admin_request(rid, db, admin)


# ---------------------------------------------------------------- statistics ----

def hours(m) -> float:
    return round((m or 0) / 60, 1)


@router.get("/stats")
def stats(days: int = Query(30, ge=0, le=3650), db: Session = Depends(get_db), _: User = Depends(current_admin)):
    now = datetime.now(timezone.utc)
    reset = stats_since(db)  # «Сбросить статистику» moves the start forward
    since = max(now - timedelta(days=days) if days else reset, reset)
    start = since if reset.year > 2000 and since == reset else (
        db.execute(select(func.min(Order.created_at))).scalar() or now)
    # the chart covers the chosen period; the averages use only the days since the reset
    period_days = days or max(1, (now - start).days + 1)
    live_days = min(period_days, max(1, (now - start).days + 1)) if since == reset else period_days
    cs = calc_settings(db)
    orders = list(db.execute(select(Order).where(Order.created_at >= since)).scalars())
    live = [o for o in orders if o.status != "cancelled"]
    ids = [o.id for o in live]
    lines = list(db.execute(select(OrderItem).where(OrderItem.order_id.in_(ids))).scalars()) if ids else []
    revenue = sum((o.total for o in live), Decimal(0))
    cost = sum((o.cost for o in live), Decimal(0))
    pieces = sum(i.qty for i in lines)
    print_min = sum(o.print_minutes for o in live)
    grams = sum((o.grams for o in live), Decimal(0))

    # top products
    by_p: dict[Any, dict] = {}
    for i in lines:
        k = i.product_id or ("custom:" + i.title)
        e = by_p.setdefault(k, {"product_id": i.product_id, "title": i.title, "qty": 0, "revenue": 0.0, "print_hours": 0.0,
                                "profit": 0.0, "orders": set()})
        e["qty"] += i.qty
        e["revenue"] += float(i.price * i.qty)
        e["profit"] += float((i.price - i.cost) * i.qty)
        e["print_hours"] += i.print_minutes * (i.qty - i.from_stock) / 60
        e["orders"].add(i.order_id)
    prods = {p.id: p for p in db.execute(select(Product)).scalars()}
    top = []
    for e in by_p.values():
        p = prods.get(e["product_id"])
        e["orders"] = len(e["orders"])
        e["views"] = p.views if p else None
        e["conversion"] = round(e["orders"] / p.views * 100, 1) if p and p.views else None
        e["avg_price"] = round(e["revenue"] / e["qty"], 2) if e["qty"] else 0
        e["revenue"], e["profit"], e["print_hours"] = round(e["revenue"], 2), round(e["profit"], 2), round(e["print_hours"], 1)
        top.append(e)
    top.sort(key=lambda e: (-e["qty"], -e["revenue"]))

    # per day
    daily = defaultdict(lambda: {"orders": 0, "revenue": 0.0, "print_hours": 0.0})
    weekday = [{"orders": 0, "revenue": 0.0} for _ in range(7)]
    for o in live:
        d = o.created_at.astimezone(timezone.utc).date().isoformat()
        daily[d]["orders"] += 1
        daily[d]["revenue"] += float(o.total)
        daily[d]["print_hours"] += o.print_minutes / 60
        wd = o.created_at.weekday()
        weekday[wd]["orders"] += 1
        weekday[wd]["revenue"] += float(o.total)
    span = min(period_days, 366)
    series = []
    for k in range(span - 1, -1, -1):
        d = (now - timedelta(days=k)).date().isoformat()
        v = daily.get(d, {"orders": 0, "revenue": 0.0, "print_hours": 0.0})
        series.append({"date": d, "orders": v["orders"], "revenue": round(v["revenue"], 2), "print_hours": round(v["print_hours"], 1)})

    # materials
    mats = defaultdict(float)
    for i in lines:
        p = prods.get(i.product_id)
        mats[(p.material if p and p.material else "другое")] += float(i.grams) * (i.qty - i.from_stock)

    # printer load
    q = queue_data(db, cs)
    capacity = cs["printers"] * cs["hours_per_day"]
    demand = print_min / 60 / live_days
    by_status = dict(db.execute(select(Order.status, func.count()).where(Order.created_at >= reset)
                                .group_by(Order.status)).all())
    reqs = list(db.execute(select(CustomRequest.status).where(CustomRequest.created_at >= since)).scalars())
    return {
        "days": days, "period_days": period_days,
        "reset_at": stamp(reset) if reset.year > 2000 else None,
        "kpi": {"orders": len(live), "cancelled": len(orders) - len(live), "revenue": f(revenue), "cost": f(cost),
                "profit": f(revenue - cost), "avg_check": round(float(revenue) / len(live), 2) if live else 0,
                "pieces": pieces, "avg_piece_price": round(float(revenue) / pieces, 2) if pieces else 0,
                "print_hours": hours(print_min), "plastic_kg": round(float(grams) / 1000, 2),
                "margin_pct": round(float((revenue - cost) / revenue * 100), 1) if revenue else 0,
                "requests": len(reqs), "requests_ordered": sum(1 for s in reqs if s == "ordered")},
        "by_status": {s: by_status.get(s, 0) for s in ORDER_STATUSES}, "labels": ORDER_LABELS,
        "top": top[:20], "series": series,
        "weekday": [{"day": n, **w} for n, w in zip(["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], weekday)],
        "materials": [{"material": k, "kg": round(v / 1000, 2)} for k, v in sorted(mats.items(), key=lambda x: -x[1])],
        "load": {"printers": cs["printers"], "hours_per_day": cs["hours_per_day"], "capacity_per_day": capacity,
                 "queue_hours": q["total_hours"], "queue_orders": len(q["items"]),
                 "days_to_clear": round(q["total_hours"] / capacity, 1) if capacity else None,
                 "demand_per_day": round(demand, 1), "utilization_pct": round(demand / capacity * 100) if capacity else None,
                 "forecast_week_hours": round(demand * 7, 1),
                 "printers_needed": max(1, math.ceil(demand / (cs["hours_per_day"] * 0.8))) if demand else cs["printers"]},
    }


def queue_data(db: Session, cs: dict) -> dict:
    """Open orders in the order they will be printed, with an estimated finish date for each."""
    rows = list(db.execute(select(Order).where(Order.status.in_(OPEN))
                           .order_by(Order.status != "printing", Order.due_date.is_(None), Order.due_date, Order.id)).scalars())
    capacity = max(0.1, cs["printers"] * cs["hours_per_day"])
    now = datetime.now(timezone.utc)
    acc = 0.0
    out = []
    for o in rows:
        acc += o.print_minutes / 60
        eta = now + timedelta(days=acc / capacity)
        late = bool(o.due_date and eta.date() > o.due_date.date())
        out.append({"id": o.id, "status": o.status, "status_label": ORDER_LABELS[o.status], "name": o.name,
                    "hours": hours(o.print_minutes), "cum_hours": round(acc, 1), "eta": eta.date().isoformat(),
                    "due_date": o.due_date.date().isoformat() if o.due_date else None, "late": late,
                    "items": [f"{i.title} × {i.qty - i.from_stock}" for i in order_lines(db, o.id) if i.qty - i.from_stock > 0]})
    return {"items": out, "total_hours": round(acc, 1), "capacity_per_day": capacity}



class StatsReset(BaseModel):
    views: bool = True


@router.post("/stats/reset")
def reset_stats(data: StatsReset, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    """Start the statistics again from now: views go to zero, orders and requests before this moment are no longer
    counted in the statistics and in the «popular» order. The orders themselves stay in the «Заказы» tab."""
    from .models import ShopSetting
    now = datetime.now(timezone.utc)
    if data.views:
        for p in db.execute(select(Product).where(Product.views > 0)).scalars():
            p.views = 0
    row = db.get(ShopSetting, "stats") or ShopSetting(key="stats", data={})
    row.data = {**(row.data or {}), "since": now.timestamp(), "by": user.login}
    db.add(row)
    db.commit()
    return {"ok": True, "since": int(now.timestamp())}

@router.get("/queue")
def queue(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return queue_data(db, calc_settings(db))


@router.post("/telegram/test")
def telegram_test(_: User = Depends(current_admin)):
    """«Проверить Telegram» in the settings: sends a test message and says what Telegram answered."""
    from .config import settings as cfg
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        raise HTTPException(400, "В .env на сервере не заполнены TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID "
                                 "(после правки .env нужен systemctl restart kartochki)")
    from .shop import tg_send
    try:
        r = tg_send("✅ Проверка: уведомления магазина работают", timeout=15)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, "Сервер не достучался до api.telegram.org (похоже, Telegram заблокирован у хостинга). "
                                 f"Укажи TELEGRAM_PROXY в .env или пользуйся уведомлениями на почту. Ошибка: {e}")
    if r.status_code != 200:
        d = r.json().get("description", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        hint = {401: "неверный токен бота", 400: "неверный chat id, или бот не добавлен в этот чат",
                403: "бот заблокирован или удалён из чата: нажми у бота Start"}.get(r.status_code, "")
        raise HTTPException(400, f"Telegram ответил: {d}" + (f" ({hint})" if hint else ""))
    return {"ok": True}


@router.put("/products/{pid}/tile")
async def set_tile(pid: int, file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """The catalogue preview drawn by the builder: the card without price plate, badges and description."""
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Товар не найден")
    try:
        p.tile = jpeg(await file.read(), 520, 84)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Это не картинка")
    db.commit()
    return {"ok": True}


@router.delete("/orders/{oid}", status_code=204)
def delete_order(oid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """Removes an order for good (test orders, duplicates). Items taken from stock for an unfinished order go back."""
    o = db.get(Order, oid)
    if o:
        if o.status not in ("done", "shipped", "cancelled"):
            return_stock(db, o)
        for i in order_lines(db, oid):
            db.delete(i)
        for e in order_events(db, oid):
            db.delete(e)
        db.flush()
        db.delete(o)
        db.commit()
    return Response(status_code=204)


class AdminLine(BaseModel):
    product_id: Optional[int] = None
    title: str = Field(default="", max_length=300)  # a line without a product from the shop
    qty: int = Field(ge=1, le=999)
    color: int = 0
    price: Optional[float] = Field(default=None, ge=0, le=10_000_000)  # empty = shop price (with the colour)
    note: str = Field(default="", max_length=300)


class AdminOrderIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=160)
    delivery: str = Field(default="pickup", max_length=40)
    address: str = Field(default="", max_length=1000)
    comment: str = Field(default="", max_length=3000)
    source: str = Field(default="", max_length=60)
    status: str = Field(default="confirmed", max_length=20)
    paid: bool = False
    take_stock: bool = True
    items: list[AdminLine] = Field(min_length=1, max_length=100)


@router.post("/orders")
def create_admin_order(data: AdminOrderIn, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """An order that came outside the site (MAX, phone, fair): it goes to the same list, queue and statistics."""
    import secrets as _s
    from .shop import active_colors, allowed_colors, color_delta, notify  # noqa: F401
    if data.status not in ORDER_STATUSES:
        raise HTTPException(400, "Неизвестный статус")
    if data.delivery not in DELIVERY:
        raise HTTPException(400, "Неизвестный способ доставки")
    o = Order(token=_s.token_urlsafe(18), user_id=None, status=data.status, name=clean(data.name, 160),
              phone=clean(data.phone, 60), email=clean(data.email, 160), delivery=data.delivery,
              address=clean(data.address, 1000), comment=clean(data.comment, 3000), source=clean(data.source, 60),
              admin_note="", total=0, cost=0, print_minutes=0, grams=0, paid=data.paid)
    db.add(o)
    db.flush()
    cs, active = calc_settings(db), active_colors(db)
    total = cost = Decimal(0)
    minutes, grams = 0, Decimal(0)
    for ln in data.items:
        if ln.product_id:
            p = db.get(Product, ln.product_id, with_for_update=True)
            if not p:
                raise HTTPException(400, "Товар не найден")
            c = next((x for x in allowed_colors(p, active) if x.id == ln.color), None)
            dprice, dcost = color_delta(p, c, cs)
            price = Decimal(str(round(ln.price, 2))) if ln.price is not None else max(p.price + Decimal(dprice), Decimal(1))
            unit_cost = (p.cost or 0) + Decimal(str(dcost))
            from_stock = min(p.stock or 0, ln.qty) if data.take_stock else 0
            p.stock = (p.stock or 0) - from_stock
            db.add(OrderItem(order_id=o.id, product_id=p.id, title=p.title, price=price, cost=unit_cost, qty=ln.qty,
                             print_minutes=p.print_minutes or 0, grams=p.grams or 0, note=clean(ln.note, 300),
                             from_stock=from_stock, color=c.name if c else ""))
            minutes += (p.print_minutes or 0) * (ln.qty - from_stock)
            grams += (p.grams or 0) * (ln.qty - from_stock)
        else:
            if not ln.title.strip() or ln.price is None:
                raise HTTPException(400, "Для позиции не из магазина нужны название и цена")
            price, unit_cost = Decimal(str(round(ln.price, 2))), Decimal(0)
            db.add(OrderItem(order_id=o.id, product_id=None, title=clean(ln.title, 300), price=price, cost=0, qty=ln.qty,
                             print_minutes=0, grams=0, note=clean(ln.note, 300), from_stock=0, color=""))
        total += price * ln.qty
        cost += unit_cost * ln.qty
    o.total, o.cost, o.print_minutes, o.grams = total, cost, minutes, grams
    add_event(db, order_id=o.id, who_=admin.name, status=o.status,
              text="Заказ добавлен администратором" + (f" (откуда: {o.source})" if o.source else ""))
    db.commit()
    return {"id": o.id, "token": o.token, "total": f(total)}

