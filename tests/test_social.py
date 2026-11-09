"""Carts not ordered yet, favourites, reviews with moderation, deleting orders, catalogue previews."""
import uuid

from tests.test_shop import admin_client, client, png_bytes, publish


def user_client():
    c = client()
    assert c.post("/api/auth/register", json={"login": "u" + uuid.uuid4().hex[:8], "password": "секрет123"}).status_code == 200
    return c


def test_carts_favorites_reviews_and_order_delete():
    a = admin_client()
    _, pub = publish(a, title="Котик для отзывов", extra={"shopStock": "3"})
    pid = pub["id"]
    g = client()
    tok = "t" + uuid.uuid4().hex
    # cart: seen by the admin, gone after an empty cart is sent
    assert g.put("/api/shop/cart", json={"token": "bad", "items": []}).status_code == 400
    assert g.put("/api/shop/cart", json={"token": tok, "items": [{"id": pid, "qty": 2}, {"id": 999999, "qty": 1}]}).status_code == 200
    carts = a.get("/api/admin/carts").json()
    mine = next(c for c in carts["items"] if c["id"] == tok)
    assert mine["user"] is None and mine["items"][0]["qty"] == 2 and len(mine["items"]) == 1 and mine["total"] == 2580
    assert client().get("/api/admin/carts").status_code == 401
    g.put("/api/shop/cart", json={"token": tok, "items": []})
    assert all(c["id"] != tok for c in a.get("/api/admin/carts").json()["items"])

    # favourites for a signed-in buyer
    u = user_client()
    assert client().get("/api/shop/favorites").status_code == 401
    assert u.post("/api/shop/favorites", json={"ids": [pid, 999999]}).json()["ids"] == [pid]
    assert [p["id"] for p in g.get(f"/api/shop/products?ids={pid}").json()["items"]] == [pid]
    assert u.delete(f"/api/shop/favorites/{pid}").json()["ids"] == []

    # reviews: hidden until approved, rating counts only approved ones
    files = [("photos", ("a.png", png_bytes(), "image/png")), ("photos", ("b.png", png_bytes((0, 0, 255, 255)), "image/png"))]
    assert g.post(f"/api/shop/products/{pid}/reviews", data={"name": "Оля", "rating": "5", "text": "Супер"}).status_code == 400  # no consent
    assert g.post(f"/api/shop/products/{pid}/reviews", data={"name": "Оля", "rating": "7", "consent": "1"}).status_code == 400
    r = g.post(f"/api/shop/products/{pid}/reviews", data={"name": "Оля", "rating": "5", "text": "Супер котик", "consent": "1"}, files=files)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    u.post(f"/api/shop/products/{pid}/reviews", data={"name": "Петя", "rating": "3", "consent": "1"})
    assert g.get(f"/api/shop/products/{pid}/reviews").json()["count"] == 0
    pend = a.get("/api/admin/reviews").json()
    rv = next(x for x in pend["items"] if x["id"] == rid)
    assert len(rv["photos"]) == 2 and rv["product_title"] == "Котик для отзывов"
    assert g.get(rv["photos"][0]["thumb"]).status_code == 404  # not published yet
    assert a.get(rv["photos"][0]["thumb"]).status_code == 200
    assert a.patch(f"/api/admin/reviews/{rid}", json={"status": "approved"}).status_code == 200
    pub_r = g.get(f"/api/shop/products/{pid}/reviews").json()
    assert pub_r["count"] == 1 and pub_r["rating"] == 5 and pub_r["items"][0]["text"] == "Супер котик"
    assert g.get(pub_r["items"][0]["photos"][1]["url"]).headers["content-type"] == "image/jpeg"
    item = next(p for p in g.get("/api/shop/products").json()["items"] if p["id"] == pid)
    assert item["rating"] == 5 and item["reviews"] == 1
    assert g.get(f"/api/shop/products/{pid}").json()["reviews"] == 1
    assert a.delete(f"/api/admin/reviews/{rid}").status_code == 204
    assert g.get(f"/api/shop/products/{pid}/reviews").json()["count"] == 0

    # deleting an order gives the items back to stock
    o = g.post("/api/shop/orders", json={"consent": True, "terms": True, "name": "Оля", "phone": "1",
                                         "items": [{"product_id": pid, "qty": 2}]}).json()
    assert a.get(f"/api/shop/products/{pid}").json()["stock"] == 1
    assert client().delete(f"/api/admin/orders/{o['id']}").status_code == 401
    assert a.delete(f"/api/admin/orders/{o['id']}").status_code == 204
    assert a.get(f"/api/admin/orders/{o['id']}").status_code == 404
    assert a.get(f"/api/shop/products/{pid}").json()["stock"] == 3


def test_catalogue_tile():
    a = admin_client()
    _, pub = publish(a, title="Плитка")
    pid = pub["id"]
    item = next(p for p in client().get("/api/shop/products").json()["items"] if p["id"] == pid)
    assert item["tile"].startswith(f"/api/shop/products/{pid}/")
    assert a.put(f"/api/admin/products/{pid}/tile", files={"file": ("t.png", png_bytes((10, 200, 10, 255), (300, 400)), "image/png")}).status_code == 200
    item = next(p for p in client().get("/api/shop/products").json()["items"] if p["id"] == pid)
    assert "/tile" in item["tile"] and client().get(item["tile"]).headers["content-type"] == "image/jpeg"
    from app.shop import tile_from_card
    from PIL import Image
    import io
    card = io.BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(card, "JPEG")
    t = Image.open(io.BytesIO(tile_from_card(card.getvalue(), "info")))
    assert t.size == (390, 520)
    assert tile_from_card(card.getvalue(), "clean") is None


def test_admin_order_and_favorites_stats():
    a = admin_client()
    _, pub = publish(a, title="Котик из MAX", extra={"shopStock": "2"})
    pid = pub["id"]
    body = {"name": "Аня из MAX", "phone": "+7 900", "source": "MAX", "paid": True,
            "items": [{"product_id": pid, "qty": 3}, {"title": "Брелок на заказ", "qty": 2, "price": 150}]}
    assert client().post("/api/admin/orders", json=body).status_code == 401
    assert a.post("/api/admin/orders", json={**body, "items": [{"title": "без цены", "qty": 1}]}).status_code == 400
    r = a.post("/api/admin/orders", json=body)
    assert r.status_code == 200, r.text
    o = a.get(f"/api/admin/orders/{r.json()['id']}").json()
    assert o["source"] == "MAX" and o["status"] == "confirmed" and o["paid"] and len(o["items"]) == 2
    assert o["items"][0]["from_stock"] == 2 and float(o["total"]) == 3 * 1290 + 300
    assert a.get(f"/api/shop/products/{pid}").json()["stock"] == 0

    # favourites of a guest reach the admin's «Отложенные» block
    g = client()
    tok = "f" + uuid.uuid4().hex
    assert g.put("/api/shop/cart", json={"token": tok, "items": [], "favs": [pid, 999999]}).status_code == 200
    favs = a.get("/api/admin/carts").json()["favs"]
    assert any(t["product_id"] == pid for t in favs["top"]) and any(v["id"] == tok for v in favs["list"])
    g.put("/api/shop/cart", json={"token": tok, "items": [], "favs": []})
    assert all(v["id"] != tok for v in a.get("/api/admin/carts").json()["favs"]["list"])


def test_multicolor_price_confirmed_by_admin():
    a = admin_client()
    _, pub = publish(a, title="Котик радужный", extra={"shopStock": "5"})
    pid = pub["id"]
    c1 = a.post("/api/admin/colors", data={"name": "Мульти красный " + uuid.uuid4().hex[:4], "hex": "#ff0000"}).json()
    c2 = a.post("/api/admin/colors", data={"name": "Мульти синий " + uuid.uuid4().hex[:4], "hex": "#0000ff"}).json()
    g = client()
    base = {"consent": True, "terms": True, "name": "Оля", "phone": "1"}
    assert g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 1, "colors": [c1["id"], 999999]}]}).status_code == 400
    r = g.post("/api/shop/orders", json={**base, "items": [{"product_id": pid, "qty": 2, "colors": [c1["id"], c2["id"]]}]})
    assert r.status_code == 200, r.text
    oid, tok = r.json()["id"], r.json()["token"]
    o = a.get(f"/api/admin/orders/{oid}").json()
    it = o["items"][0]
    assert it["price_pending"] and " + " in it["color"] and it["from_stock"] == 0 and o["price_pending"]
    assert a.get(f"/api/shop/products/{pid}").json()["stock"] == 5  # printed, not taken from the shelf
    assert client().patch(f"/api/admin/orders/{oid}/items/{it['id']}", json={"price": 500}).status_code == 401
    o = a.patch(f"/api/admin/orders/{oid}/items/{it['id']}", json={"price": 500, "print_minutes": 90}).json()
    assert not o["items"][0]["price_pending"] and o["total"] == 1000 and not o["price_pending"]
    assert any("подтверждена" in e["text"] for e in o["events"])
