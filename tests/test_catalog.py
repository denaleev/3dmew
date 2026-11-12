"""Colours with filament photos, product photos/videos, filters, admin editing, feedback, own spool price."""
from app import pricing
from tests.test_shop import admin_client, client, png_bytes, publish


def test_own_spool_price():
    base = {"material": "PLA", "grams": 100, "hours": 1, "minutes": 0, "pieces": 1}
    a = pricing.calc(base, dict(pricing.DEFAULTS))
    b = pricing.calc({**base, "kg_price": 3200}, dict(pricing.DEFAULTS))
    assert a["kg_price"] == 1600 and b["kg_price"] == 3200 and b["plastic"] == a["plastic"] * 2


def test_colors_media_filters_and_feedback():
    a = admin_client()
    _, pub = publish(a, title="Котик цветной", extra={"shopStock": "4", "calcKg": "2500"})
    pid = pub["id"]
    c1 = a.post("/api/admin/colors", data={"name": "Silk розовый", "hex": "#e8508a", "material": "Silk PLA"},
                files={"photo": ("spool.png", png_bytes((232, 80, 138, 255), (300, 300)), "image/png")}).json()
    c2 = a.post("/api/admin/colors", data={"name": "Бирюза", "hex": "#28b4aa", "hex2": "#ffffff"}).json()
    assert c1["photo"] and c2["hex2"] == "#ffffff"
    assert a.post("/api/admin/colors", data={"name": "x", "hex": "red"}).status_code == 400
    assert client().post("/api/admin/colors", data={"name": "x"}).status_code == 401
    assert a.get(c1["photo"]).headers["content-type"] == "image/jpeg"

    # stock and own spool price came from the builder
    full = a.get(f"/api/shop/products/{pid}").json()
    assert full["stock"] == 4 and full["item_id"]
    assert a.patch(f"/api/admin/products/{pid}", json={"colors": [c1["id"], c2["id"], 999999], "features": "Материал: Silk PLA"}).status_code == 200
    g = client()
    p = g.get(f"/api/shop/products/{pid}").json()
    assert sorted(c["name"] for c in p["color_list"]) == ["Silk розовый", "Бирюза"] and "item_id" not in p
    assert p["material"] == "PETG"  # the calculator material wins over the features line

    # media: photos and a video; Range requests for the video
    r = a.post(f"/api/admin/products/{pid}/media", files=[("files", ("a.png", png_bytes(), "image/png")),
                                                          ("files", ("clip.mp4", b"\x00" * 5000, "video/mp4"))])
    media = r.json()["media"]
    assert [m["kind"] for m in media] == ["image", "video"]
    v = g.get(media[1]["url"], headers={"range": "bytes=100-199"})
    assert v.status_code == 206 and len(v.content) == 100 and v.headers["content-range"] == "bytes 100-199/5000"
    assert a.post(f"/api/admin/products/{pid}/media", files=[("files", ("x.exe", b"MZ", "application/x-msdownload"))]).status_code == 400
    assert a.put(f"/api/admin/products/{pid}/media", json={"ids": [media[1]["id"], media[0]["id"]]}).status_code == 200
    assert [m["kind"] for m in g.get(f"/api/shop/products/{pid}").json()["media"]] == ["video", "image"]
    assert a.post(f"/api/admin/products/{pid}/media/{media[0]['id']}/main").status_code == 200

    # filters and groups
    lst = g.get(f"/api/shop/products?color={c1['id']}").json()
    assert pid in [x["id"] for x in lst["items"]] and any(c["id"] == c1["id"] for c in lst["colors"])
    assert pid in [x["id"] for x in g.get("/api/shop/products?in_stock=1").json()["items"]]
    assert pid not in [x["id"] for x in g.get("/api/shop/products?pmax=10").json()["items"]]
    assert any(m["name"] == "PETG" for m in lst["materials"]) and lst["categories"][0]["count"]

    # colour is required and stored in the order
    base = {"consent": True, "terms": True, "name": "Оля", "phone": "1"}
    bad = g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 1, "color": 999999}]})
    assert bad.status_code == 400 and "цвет" in bad.json()["detail"]
    # no colour picked: the standard one (set in the builder) is used
    assert a.patch(f"/api/admin/products/{pid}", json={"default_color": c2["id"]}).status_code == 200
    d = g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 1}]})
    assert d.status_code == 200, d.text
    assert a.get(f"/api/admin/orders/{d.json()['id']}").json()["items"][0]["color"] == "Бирюза"
    assert g.get(f"/api/shop/products/{pid}").json()["color_list"][0]["mark"] == "default"
    r = g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 1, "color": c2["id"]}]})
    assert r.status_code == 200, r.text
    assert a.get(f"/api/admin/orders/{r.json()['id']}").json()["items"][0]["color"] == "Бирюза"

    # hide from the shop: hidden for customers, visible for the admin with all=1
    a.patch(f"/api/admin/products/{pid}", json={"published": False})
    assert g.get(f"/api/shop/products/{pid}").status_code == 404
    assert pid in [x["id"] for x in a.get("/api/shop/products?all=1").json()["items"]]
    assert pid not in [x["id"] for x in g.get("/api/shop/products?all=1").json()["items"]]

    # deleting a colour removes it from products
    assert a.delete(f"/api/admin/colors/{c2['id']}").status_code == 204
    assert a.get(f"/api/shop/products/{pid}").json()["colors"] == [c1["id"]]

    # a product made without the builder
    np = a.post("/api/admin/products", json={"title": "Новый", "price": 99}).json()
    assert a.get(f"/api/shop/products/{np['id']}").json()["published"] is False

    # feedback
    assert g.post("/api/shop/feedback", json={"name": "Ира", "contact": "ira@ex.ru", "text": "Привет"}).status_code == 400
    assert g.post("/api/shop/feedback", json={"name": "Ира", "contact": "ira@ex.ru", "text": "Привет", "consent": True}).status_code == 200
    fb = a.get("/api/admin/feedback").json()
    assert fb["items"][0]["text"] == "Привет" and fb["email"] == "mew.shop@yandex.ru"
    fid = fb["items"][0]["id"]
    assert client().delete(f"/api/admin/feedback/{fid}").status_code == 401
    assert a.delete(f"/api/admin/feedback/{fid}").status_code == 204
    assert all(x["id"] != fid for x in a.get("/api/admin/feedback").json()["items"])

    # about text is editable and has a default (an empty value falls back to it)
    a.put("/api/admin/settings", json={"shop": {"about": ""}})
    info = g.get("/api/shop/info").json()
    assert "творческий проект" in info["about"] and info["footer_text"].startswith("© 2026")
    a.put("/api/admin/settings", json={"shop": {"about": "Новый текст", "max": "https://max.ru/u/test"}})
    info = g.get("/api/shop/info").json()
    assert info["about"] == "Новый текст" and info["max"] == "https://max.ru/u/test"


def test_max_bot_post(monkeypatch):
    from app import maxbot
    from app.config import settings
    from app.db import SessionLocal
    from app.models import ShopSetting
    with SessionLocal() as db:  # start without a chosen group
        row = db.get(ShopSetting, "max_bot")
        if row:
            db.delete(row)
            db.commit()
    a = admin_client()
    _, pub = publish(a, title="Для MAX")
    monkeypatch.setattr(settings, "MAX_BOT_TOKEN", "")
    assert a.post(f"/api/admin/max/post/{pub['id']}").status_code == 400  # not connected
    monkeypatch.setattr(settings, "MAX_BOT_TOKEN", "tkn")
    monkeypatch.setattr(settings, "PUBLIC_URL", "https://3dmew.ru")
    sent = []

    def fake_call(method, path, **kw):
        if path == "/me":
            return {"name": "Мяу-бот"}
        if path == "/chats":
            return {"chats": [{"chat_id": -77, "title": "3DМяу", "type": "chat"}, {"chat_id": 5, "type": "dialog"}]}
        if path == "/uploads":
            return {"url": "https://upload.example/x"}
        if path == "/messages":
            sent.append((kw["params"], kw["json"]))
            return {"message": {}}
        raise AssertionError(path)

    class R:
        content = b"1"
        def raise_for_status(self): pass
        def json(self): return {"token": "img-token"}

    monkeypatch.setattr(maxbot, "call", fake_call)
    monkeypatch.setattr(maxbot.httpx, "post", lambda *a, **k: R())
    monkeypatch.setattr(maxbot.time, "sleep", lambda s: None)
    st = a.get("/api/admin/max/status").json()
    assert st["bot"] == "Мяу-бот" and [c["chat_id"] for c in st["chats"]] == [-77]
    assert a.post(f"/api/admin/max/post/{pub['id']}").status_code == 400  # no group yet
    assert a.put("/api/admin/max/chat", json={"chat_id": -77, "chat_title": "3DМяу"}).status_code == 200
    r = a.post(f"/api/admin/max/post/{pub['id']}")
    assert r.status_code == 200, r.text
    params, body = sent[0]
    assert params == {"chat_id": -77} and "<b>Для MAX</b>" in body["text"]
    assert body["attachments"][0] == {"type": "image", "payload": {"token": "img-token"}}
    assert body["attachments"][1]["payload"]["buttons"][0][0]["url"].endswith(f"/p/{pub['id']}")
    assert client().post(f"/api/admin/max/post/{pub['id']}").status_code == 401


def test_favicon_and_payment():
    a = admin_client()
    g = client()
    assert g.get("/api/shop/favicon/64.png").headers["content-type"] == "image/png"
    assert a.put("/api/admin/favicon", files={"file": ("i.png", png_bytes((10, 200, 10, 255), (300, 200)), "image/png")}).status_code == 200
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(g.get("/api/shop/favicon/180.png").content))
    assert im.size == (180, 180) and im.getpixel((90, 90))[1] == 200
    assert a.put("/api/admin/favicon", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 400
    assert client().put("/api/admin/favicon", files={"file": ("i.png", png_bytes(), "image/png")}).status_code == 401
    assert a.delete("/api/admin/favicon").status_code == 204
    assert g.get("/favicon.ico", follow_redirects=False).status_code in (302, 307)
    _, pub = publish(a, title="Оплата")
    base = {"consent": True, "terms": True, "name": "Оля", "phone": "1", "items": [{"product_id": pub["id"], "qty": 1}]}
    assert g.post("/api/shop/orders", json={**base, "payment": "online"}).status_code == 400
    r = g.post("/api/shop/orders", json=base)
    assert r.status_code == 200
    ev = a.get(f"/api/admin/orders/{r.json()['id']}").json()["events"]
    assert "Оплата: при получении" in ev[0]["text"]


def test_categories_color_price_and_stats_reset():
    a = admin_client()
    g = client()
    _, pub = publish(a, title="Котик дорогой", extra={"shopCat": "Котики-тест"})
    pid = pub["id"]
    # groups: shown as labels in the admin order; renaming moves the products
    cats = a.get("/api/admin/categories").json()
    me = next(c for c in cats if c["name"] == "Котики-тест")
    assert me["count"] >= 1
    assert a.post("/api/admin/categories", json={"name": "котики-ТЕСТ"}).status_code == 409
    new = a.post("/api/admin/categories", json={"name": "Пустая группа"})
    assert new.status_code == 200 or new.status_code == 409
    assert a.patch(f"/api/admin/categories/{me['id']}", json={"name": "Котики-2"}).json()["count"] >= 1
    assert g.get(f"/api/shop/products/{pid}").json()["category"] == "Котики-2"
    names = [c["name"] for c in g.get("/api/shop/products").json()["categories"]]
    assert "Котики-2" in names and "Пустая группа" not in names  # empty groups are not shown
    assert a.patch(f"/api/admin/categories/{me['id']}", json={"active": False}).status_code == 200
    assert "Котики-2" not in [c["name"] for c in g.get("/api/shop/products").json()["categories"]]
    assert a.delete(f"/api/admin/categories/{me['id']}").status_code == 204
    assert g.get(f"/api/shop/products/{pid}").json()["category"] == ""

    # a colour with its own plastic price changes the price of the product
    cheap = a.post("/api/admin/colors", data={"name": "Тест-база", "hex": "#ffffff", "kg_price": "1700"}).json()
    dear = a.post("/api/admin/colors", data={"name": "Тест-шёлк", "hex": "#e8508a", "kg_price": "3700"}).json()
    plain = a.post("/api/admin/colors", data={"name": "Тест-без-цены", "hex": "#000000"}).json()
    assert dear["kg_price"] == 3700 and plain["kg_price"] is None
    assert a.post("/api/admin/colors", data={"name": "x", "kg_price": "abc"}).status_code == 400
    assert a.patch(f"/api/admin/products/{pid}", json={"colors": [cheap["id"], dear["id"], plain["id"]], "grams": 200}).status_code == 200
    full = a.get(f"/api/shop/products/{pid}").json()
    assert full["grams"] == 200 and full["base_kg_price"] == 1700  # PETG from the calculator
    d = {c["id"]: c for c in g.get(f"/api/shop/products/{pid}").json()["color_list"]}
    assert d[cheap["id"]]["delta"] == 0 and d[plain["id"]]["delta"] == 0
    assert d[dear["id"]]["delta"] > 0 and d[dear["id"]]["delta"] % 10 == 0
    assert d[dear["id"]]["price"] == full["price"] + d[dear["id"]]["delta"]
    base = {"consent": True, "terms": True, "name": "Оля", "phone": "1"}
    r = g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 2, "color": dear["id"]}]})
    assert r.status_code == 200 and r.json()["total"] == 2 * d[dear["id"]]["price"]

    # statistics reset: views to zero, older orders are not counted any more, but stay in the list
    assert a.get("/api/admin/stats?days=0").json()["kpi"]["orders"] >= 1
    assert client().post("/api/admin/stats/reset", json={}).status_code == 401
    assert a.post("/api/admin/stats/reset", json={}).status_code == 200
    st = a.get("/api/admin/stats?days=0").json()
    assert st["kpi"]["orders"] == 0 and st["reset_at"] and st["top"] == []
    assert a.get(f"/api/shop/products/{pid}").json()["sold"] == 0
    assert any(o["id"] == r.json()["id"] for o in a.get("/api/admin/orders").json()["items"])
    r2 = g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 1, "color": cheap["id"]}]})
    assert a.get("/api/admin/stats?days=30").json()["kpi"]["orders"] == 1

    # favicon: a new upload gives a new version, the picture is never cached for long
    v0 = g.get("/api/shop/info").json()["favicon_v"]
    a.put("/api/admin/favicon", files={"file": ("i.png", png_bytes(), "image/png")})
    assert g.get("/api/shop/info").json()["favicon_v"] != v0 or v0 == 0
    assert g.get("/api/shop/favicon/64.png").headers["cache-control"] == "no-cache"
    for c in (cheap, dear, plain):
        a.delete(f"/api/admin/colors/{c['id']}")


def test_link_preview_tags():
    a = admin_client()
    a.put("/api/admin/settings", json={"shop": {"meta_description": "Милые котики & антистрессы на 3D-принтере"}})
    h = client().get("/").text
    assert 'property="og:title"' in h and "Милые котики &amp; антистрессы" in h and "/img/logo-512.png" in h
    _, pub = publish(a, title="Котик «Тест»")
    h = client().get(f"/p/{pub['id']}").text
    assert "Котик «Тест» — 1 290 ₽" in h and f"/api/shop/products/{pub['id']}/image" in h
    assert f"location.replace('/#product/{pub['id']}')" in h
    a.put("/api/admin/settings", json={"shop": {"meta_description": ""}})


def test_publish_keeps_weight_and_by_item_lookup():
    from tests.test_shop import admin_client, publish
    a = admin_client()
    iid, pub = publish(a, title="Котик с весом", extra={"calcGrams": "", "calcH": "", "calcM": ""})
    pid = pub["id"]
    assert a.patch(f"/api/admin/products/{pid}", json={"grams": 42}).status_code == 200
    # publishing again from the builder without the calculator keeps the weight
    assert a.post(f"/api/admin/products/from-item/{iid}").status_code == 200
    r = a.get(f"/api/admin/products/by-item/{iid}").json()
    assert r["id"] == pid and r["grams"] == 42
    assert a.get("/api/admin/products/by-item/nope").status_code == 404
    # colours ticked in the builder are applied on publishing; an empty list means the whole palette
    c = a.post("/api/admin/colors", data={"name": "Цвет билдера " + iid, "hex": "#123456"}).json()
    st = {"title": "Котик с весом", "price": "500", "shopColors": f"{c['id']},999999"}
    assert a.put(f"/api/items/{iid}", json={"kind": "card", "title": "Котик с весом", "thumb": None, "state": st, "t": 2}).status_code == 200
    a.post(f"/api/admin/products/from-item/{iid}")
    assert a.get(f"/api/admin/products/by-item/{iid}").json()["colors"] == [c["id"]]
    st["shopColors"] = ""
    a.put(f"/api/items/{iid}", json={"kind": "card", "title": "Котик с весом", "thumb": None, "state": st, "t": 3})
    a.post(f"/api/admin/products/from-item/{iid}")
    assert a.get(f"/api/admin/products/by-item/{iid}").json()["colors"] == []
