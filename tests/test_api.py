"""API tests. Need a PostgreSQL database already migrated (alembic upgrade head):
    DATABASE_URL=postgresql+psycopg://cards:cards@127.0.0.1:5432/cards_test pytest -q
"""
import base64
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import User


def client():
    return TestClient(app)


def creds():
    return {"login": "Тест " + uuid.uuid4().hex[:8], "password": "секрет123"}


def test_register_login_and_password_is_hashed():
    c, cr = client(), creds()
    r = c.post("/api/auth/register", json=cr)
    assert r.status_code == 200, r.text
    assert c.get("/api/me").json()["name"] == cr["login"]
    assert c.post("/api/auth/register", json=cr).status_code == 409
    with SessionLocal() as db:
        u = db.execute(select(User).where(User.login == cr["login"].lower())).scalar_one()
        assert u.password_hash.startswith("$argon2id$") and cr["password"] not in u.password_hash
    c2 = client()
    assert c2.post("/api/auth/login", json={**cr, "password": "wrong-pass"}).status_code == 401
    assert c2.post("/api/auth/login", json=cr).status_code == 200
    assert c2.post("/api/auth/logout").status_code == 204
    assert c2.get("/api/me").json() == {"id": None}


def test_library_drafts_photos_blobs_prefs_and_isolation():
    a, b = client(), client()
    k = uuid.uuid4().hex[:8]
    a.post("/api/auth/register", json=creds())
    b.post("/api/auth/register", json=creds())
    assert a.put(f"/api/items/c1{k}", json={"kind": "card", "title": "Роза", "thumb": "data:x", "state": {"title": "Роза"}, "t": 2}).status_code == 200
    assert a.put(f"/api/items/d1{k}", json={"kind": "draft", "title": "Черновик", "t": 1}).status_code == 200
    items = a.get("/api/items").json()
    assert [i["id"] for i in items] == ["c1" + k, "d1" + k] and "state" not in items[0]
    assert a.get(f"/api/items/c1{k}").json()["state"] == {"title": "Роза"}
    # another user can't see or overwrite it
    assert b.get(f"/api/items/c1{k}").status_code == 404
    assert b.put(f"/api/items/c1{k}", json={"kind": "card", "t": 3}).status_code == 404
    assert b.get("/api/items").json() == []
    png = io.BytesIO(); Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(png, "PNG")
    r = a.put(f"/api/blobs/c1{k}", data={"product_cut": "1"}, files={"png": ("png", png.getvalue(), "image/png"), "photo": ("photo", b"\xff\xd8jpeg", "image/jpeg")})
    assert r.status_code == 200, r.text
    meta = a.get(f"/api/blobs/c1{k}").json()
    assert meta["has"] == {"png": True, "photo": True, "product": False, "manual": False}
    assert a.get(f"/api/blobs/c1{k}/png").content == png.getvalue()
    assert a.get(f"/api/blobs/c1{k}/photo").headers["content-type"] == "image/jpeg"
    assert b.get(f"/api/blobs/c1{k}/png").status_code == 404
    assert a.put(f"/api/photos/p1{k}", json={"name": "real.jpg", "size": 10, "thumb": "data:y", "t": 5}).status_code == 200
    assert a.get("/api/photos").json()[0]["name"] == "real.jpg"
    assert a.put("/api/prefs", json={"themes": [{"id": "x", "a1": "#000000", "a2": "#ffffff", "dark": False}]}).status_code == 200
    assert a.get("/api/prefs").json()["themes"][0]["id"] == "x"
    assert a.delete(f"/api/items/c1{k}").status_code == 204 and a.get(f"/api/items/c1{k}").status_code == 404
    assert a.get("/api/items/bad%20id").status_code in (404, 422)


def test_needs_login():
    c = client()
    assert c.get("/api/items").status_code == 401
    assert c.put("/api/prefs", json={}).status_code == 401


def test_recognition_fill_without_claude():
    c = client()
    with open("tests/rose.jpg", "rb") as f:
        img = base64.b64encode(f.read()).decode()
    r = c.post("/api/ai/fill", json={"fields": ["title"], "image": img})
    assert r.status_code == 200, r.text
    names = [g["name"] for g in r.json()["guesses"]]
    assert names and ("гироскоп-антистресс" in names or "роза" in names), names


def test_oauth_start_and_bad_callback(monkeypatch):
    from app.config import settings
    monkeypatch.setitem(settings.OAUTH, "yandex", ("cid", "sec"))
    c = client()
    r = c.get("/api/auth/yandex/start", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://oauth.yandex.ru/authorize?")
    r = c.get("/api/auth/yandex/callback?code=x&state=forged", follow_redirects=False)
    assert r.headers["location"] == "/?login=fail"


def test_games_page_and_scripts():
    c = client()
    r = c.get("/igry")
    assert r.status_code == 200 and "МЯУ-АРКАДА" in r.text
    for name in ("core", "previews", "blocks", "snake", "run", "bridge"):
        assert f"/games/{name}.js" in r.text
        assert c.get(f"/games/{name}.js").status_code == 200
