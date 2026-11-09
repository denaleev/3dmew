"""Shop tests: publish a card, order it, track it, custom requests, statistics, the cost formula."""
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import update

from app import pricing
from app.db import SessionLocal
from app.main import app
from app.models import User


def client():
    # every test client looks like a separate visitor, so the sign-up rate limit doesn't kick in
    return TestClient(app, headers={"x-forwarded-for": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"})


def png_bytes(color=(200, 50, 50, 255), size=(60, 80)):
    b = io.BytesIO()
    Image.new("RGBA", size, color).save(b, "PNG")
    return b.getvalue()


def admin_client():
    c = client()
    login = "Админ " + uuid.uuid4().hex[:8]
    r = c.post("/api/auth/register", json={"login": login, "password": "секрет123"})
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == r.json()["id"]).values(is_admin=True))
        db.commit()
    assert c.get("/api/me").json()["admin"] is True
    return c


def publish(c, title="Ваза «Волна»", price="1290", extra=None):
    iid = "c" + uuid.uuid4().hex[:10]
    st = {"title": title, "price": price, "old": "1590", "desc": "Красивая ваза", "feats": "Материал: PETG\nВысота: 20 см",
          "shopCat": "Вазы", "calcMat": "PETG", "calcGrams": "180", "calcH": "6", "calcM": "30", "calcN": "1",
          "calcFinish": "10", "calcExtra": "0", "calcMarkup": "", **(extra or {})}
    assert c.put(f"/api/items/{iid}", json={"kind": "card", "title": title, "thumb": None, "state": st, "t": 1}).status_code == 200
    assert c.put(f"/api/blobs/{iid}", data={"product_cut": "1"}, files={"png": ("png", png_bytes(), "image/png")}).status_code == 200
    r = c.post(f"/api/admin/products/from-item/{iid}")
    assert r.status_code == 200, r.text
    return iid, r.json()


def test_formula_example():
    s = dict(pricing.DEFAULTS)
    r = pricing.calc({"material": "PLA", "grams": 100, "hours": 5, "minutes": 0, "pieces": 1, "finish_min": 0, "extras": 0}, s)
    # plastic 100 g × 1.05 × 1600/1000 = 168; power 0.15 × 5 × 6.5 = 4.875; wear 5 × (70000/5000 + 5) = 95
    assert r["plastic"] == 168 and r["power"] == 4.88 and r["wear"] == 95
    printing = (168 + 4.875 + 95) / 0.93
    cost = printing + 10 / 60 * 400 + 30
    assert abs(r["cost"] - round(cost, 2)) < 0.01
    raw = cost * 2.2 / 0.94
    assert abs(r["raw_price"] - round(raw, 2)) < 0.01
    assert r["price"] >= raw and str(int(r["price"])).endswith(("40", "90"))
    # two pieces on one plate: half the plastic and time per piece
    r2 = pricing.calc({"material": "PLA", "grams": 100, "hours": 5, "pieces": 2}, s)
    assert r2["grams"] == 50 and r2["print_minutes"] == 150 and r2["cost"] < r["cost"]
    assert pricing.nice(763) == 790 and pricing.nice(795) == 840 and pricing.nice(87) == 89 and pricing.nice(6420) == 6490


def test_only_admin_publishes_and_manages():
    c = client()
    c.post("/api/auth/register", json={"login": "Покупатель " + uuid.uuid4().hex[:8], "password": "секрет123"})
    assert c.post("/api/admin/products/from-item/x1").status_code == 403
    assert c.get("/api/admin/orders").status_code == 403
    assert c.get("/api/admin/stats").status_code == 403
    assert client().get("/api/admin/orders").status_code == 401


def test_publish_order_track_and_stats():
    a = admin_client()
    iid, pub = publish(a)
    assert pub["new"] and pub["cost"] > 0 and pub["print_minutes"] == 390
    _, pub2 = publish(a)  # same card again → update, not a new product
    pid = pub["id"]
    # catalogue
    g = client()
    items = g.get("/api/shop/products?sort=new").json()["items"]
    p = next(i for i in items if i["id"] == pid)
    assert p["price"] == 1290 and p["old_price"] == 1590 and "cost" not in p
    full = g.get(f"/api/shop/products/{pid}").json()
    assert full["features"][0] == {"k": "Материал", "v": "PETG"}
    assert g.get(p["thumb"]).headers["content-type"] == "image/jpeg"
    # guest orders 2 pieces, one is on the shelf
    assert a.patch(f"/api/admin/products/{pid}", json={"stock": 1}).status_code == 200
    bad = g.post("/api/shop/orders", json={"consent": True, "terms": True, "name": "Оля", "items": [{"product_id": pid, "qty": 1}]})
    no_consent = g.post("/api/shop/orders", json={"name": "Оля", "phone": "1", "items": [{"product_id": pid, "qty": 1}]})
    assert no_consent.status_code == 400 and "персональных" in no_consent.json()["detail"]
    assert bad.status_code == 400  # no phone or e-mail
    r = g.post("/api/shop/orders", json={"consent": True, "terms": True, "name": "Оля", "phone": "+7 900 000-00-00", "delivery": "pickup",
                                         "items": [{"product_id": pid, "qty": 2, "note": "синий"}]})
    assert r.status_code == 200, r.text
    oid, tok = r.json()["id"], r.json()["token"]
    assert r.json()["total"] == 2580
    # tracking only with the secret token
    assert client().get(f"/api/shop/orders/{oid}").status_code == 404
    o = client().get(f"/api/shop/orders/{oid}?token={tok}").json()
    assert o["status"] == "new" and o["items"][0]["note"] == "синий" and "admin_note" not in o
    # admin sees cost and print time of the one piece that has to be printed
    ao = a.get(f"/api/admin/orders/{oid}").json()
    assert ao["print_minutes"] == 390 and ao["items"][0]["from_stock"] == 1
    q = a.get("/api/admin/queue").json()
    assert any(x["id"] == oid for x in q["items"])
    # status changes are logged with who and when
    a.patch(f"/api/admin/orders/{oid}", json={"status": "printing", "comment": "Начали печать", "due_date": "2030-01-01"})
    a.patch(f"/api/admin/orders/{oid}", json={"admin_note": "клиент постоянный", "paid": True})
    ev = a.get(f"/api/admin/orders/{oid}").json()["events"]
    assert [e["status"] for e in ev if e["status"]] == ["new", "printing"] and ev[1]["who"].startswith("Админ")
    pub_ev = client().get(f"/api/shop/orders/{oid}?token={tok}").json()["events"]
    assert all("🔒" not in e["text"] for e in pub_ev)  # private notes are hidden from the customer
    assert client().post(f"/api/shop/orders/{oid}/cancel?token={tok}").status_code == 400  # already in work
    a.patch(f"/api/admin/orders/{oid}", json={"status": "done"})
    # statistics
    s = a.get("/api/admin/stats?days=30").json()
    assert s["kpi"]["orders"] >= 1 and s["kpi"]["revenue"] >= 2580
    assert any(t["product_id"] == pid and t["qty"] >= 2 for t in s["top"])
    assert s["load"]["capacity_per_day"] == 20 and len(s["series"]) == 30
    assert a.get("/api/admin/orders.csv").text.startswith("﻿№;")
    # hidden product disappears from the shop, cancel returns shelf stock
    r = g.post("/api/shop/orders", json={"consent": True, "terms": True, "name": "Петя", "email": "p@ex.ru", "items": [{"product_id": pid, "qty": 1}]})
    oid2, tok2 = r.json()["id"], r.json()["token"]
    a.patch(f"/api/admin/products/{pid}", json={"stock": 3})
    assert client().post(f"/api/shop/orders/{oid2}/cancel?token={tok2}").status_code == 200
    assert a.patch(f"/api/admin/products/{pid}", json={"published": False}).status_code == 200
    assert client().get(f"/api/shop/products/{pid}").status_code == 404
    assert g.post("/api/shop/orders", json={"consent": True, "terms": True, "name": "Петя", "email": "p@ex.ru", "items": [{"product_id": pid, "qty": 1}]}).status_code == 400


def test_custom_request_quote_and_order():
    a = admin_client()
    c = client()
    c.post("/api/auth/register", json={"login": "Клиент " + uuid.uuid4().hex[:8], "password": "секрет123"})
    files = [("files", ("idea.png", png_bytes((10, 200, 10, 255)), "image/png")),
             ("files", ("model.stl", b"solid x\nendsolid x\n", "application/sla"))]
    r = c.post("/api/shop/requests", data={"consent": "on", "terms": "on", "name": "Иван", "phone": "123", "title": "Брелок с логотипом",
                                          "description": "Нужно 20 брелоков", "qty": "20"}, files=files)
    assert r.status_code == 200, r.text
    rid, tok = r.json()["id"], r.json()["token"]
    assert c.post("/api/shop/requests", data={"consent": "on", "terms": "on", "name": "x", "phone": "1", "description": "плохой файл"},
                  files=[("files", ("a.exe", b"MZ", "application/octet-stream"))]).status_code == 400
    mine = c.get("/api/shop/requests/mine").json()
    assert mine[0]["id"] == rid and len(mine[0]["files"]) == 2
    req = a.get(f"/api/admin/requests/{rid}").json()
    img = next(x for x in req["files"] if x["image"])
    assert a.get(img["thumb"]).headers["content-type"] == "image/jpeg"
    stl = next(x for x in req["files"] if not x["image"])
    assert a.get(stl["url"]).headers["content-disposition"].startswith("attachment")
    assert client().get(stl["url"]).status_code == 404  # strangers can't download
    assert client().get(f"/api/shop/requests/{rid}/files/{stl['id']}?token={tok}").status_code == 200
    # can't accept before a price is named
    assert c.post(f"/api/shop/requests/{rid}/accept", json={}).status_code == 400
    q = a.post("/api/shop/calc", json={"material": "PLA", "grams": 200, "hours": 8, "pieces": 20}).json()
    assert q["price"] > 0
    assert a.patch(f"/api/admin/requests/{rid}", json={"status": "quoted"}).status_code == 400
    r = a.patch(f"/api/admin/requests/{rid}", json={"quote_price": 3000, "quote_minutes": 480, "quote_grams": 200,
                                                   "quote_cost": 1200, "quote_text": "Готово за 3 дня", "status": "quoted"})
    assert r.status_code == 200 and r.json()["status"] == "quoted"
    acc = client().post(f"/api/shop/requests/{rid}/accept?token={tok}", json={"delivery": "pickup"})
    assert acc.status_code == 200, acc.text
    o = a.get(f"/api/admin/orders/{acc.json()['id']}").json()
    assert o["total"] == 3000 and o["request_id"] == rid and o["print_minutes"] == 480 and o["items"][0]["qty"] == 20
    assert a.get(f"/api/admin/requests/{rid}").json()["status"] == "ordered"


def test_settings_and_pages():
    a = admin_client()
    s = a.get("/api/admin/settings").json()
    s["calc"]["printers"] = 3
    s["calc"]["materials"]["Wood PLA"] = 2400
    s["shop"]["name"] = "Тестовая мастерская"
    r = a.put("/api/admin/settings", json={"calc": s["calc"], "shop": s["shop"]})
    assert r.json()["calc"]["printers"] == 3 and r.json()["calc"]["materials"]["Wood PLA"] == 2400
    assert client().get("/api/shop/info").json()["name"] == "Тестовая мастерская"
    a.put("/api/admin/settings", json={"calc": {**s["calc"], "printers": 1}, "shop": {"name": "3D-мастерская"}})
    for path in ("/", "/builder", "/admin"):
        assert client().get(path).status_code == 200


def test_print_files_of_a_card():
    a = admin_client()
    iid, pub = publish(a, title="Кит с файлом")
    other = client()
    other.post("/api/auth/register", json={"login": "Чужой " + uuid.uuid4().hex[:8], "password": "секрет123"})
    model = b"PK\x03\x04 fake 3mf"
    r = a.post(f"/api/items/{iid}/files", files={"file": ("Кит плита 1.3mf", model, "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")},
               data={"note": "PETG, 0.2 мм"})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["size"] == len(model) and f["note"] == "PETG, 0.2 мм"
    assert a.post(f"/api/items/{iid}/files", files={"file": ("virus.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert a.post("/api/items/nope123/files", files={"file": ("a.3mf", b"x", "x")}).status_code == 404
    lst = a.get(f"/api/items/{iid}/files").json()
    assert [x["name"] for x in lst] == ["Кит плита 1.3mf"]
    assert next(i for i in a.get("/api/items").json() if i["id"] == iid)["files"] == 1
    d = a.get(f["url"])
    assert d.content == model and "attachment" in d.headers["content-disposition"]
    # strangers and customers can't see or download it
    assert other.get(f"/api/items/{iid}/files").status_code == 404
    assert other.get(f["url"]).status_code == 404 and client().get(f["url"]).status_code == 401
    assert "files" not in client().get(f"/api/shop/products/{pub['id']}").json()
    # the admin sees the files right in the order
    r = client().post("/api/shop/orders", json={"consent": True, "terms": True, "name": "Оля", "phone": "1", "items": [{"product_id": pub["id"], "qty": 1}]})
    o = a.get(f"/api/admin/orders/{r.json()['id']}").json()
    assert o["items"][0]["files"][0]["name"] == "Кит плита 1.3mf"
    assert next(p for p in a.get("/api/admin/products").json() if p["id"] == pub["id"])["files"] == 1
    assert other.delete(f["url"]).status_code == 204 and len(a.get(f"/api/items/{iid}/files").json()) == 1  # not theirs
    assert a.delete(f["url"]).status_code == 204 and a.get(f"/api/items/{iid}/files").json() == []
