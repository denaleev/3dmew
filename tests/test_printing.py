"""Library of cut-out photos, business card / booklet layouts, QR codes."""
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import update

from app.db import SessionLocal
from app.main import app
from app.models import User


def png(size=(40, 30), color=(255, 0, 0, 128)) -> bytes:
    b = io.BytesIO()
    Image.new("RGBA", size, color).save(b, "PNG")
    return b.getvalue()


def user_client(admin: bool) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"login": "Печать " + uuid.uuid4().hex[:8], "password": "секрет123"})
    assert r.status_code == 200, r.text
    if admin:
        with SessionLocal() as db:
            db.execute(update(User).where(User.id == r.json()["id"]).values(is_admin=True))
            db.commit()
    return c


def test_builder_saves_cutouts_one_per_card():
    a = user_client(admin=True)
    src = "c" + uuid.uuid4().hex[:10]
    r = a.put(f"/api/cutouts/{src}", data={"name": "Роза кошка"}, files={"png": ("cutout.png", png(), "image/png")})
    assert r.status_code == 200, r.text
    first = r.json()
    assert (first["name"], first["w"], first["h"]) == ("Роза кошка", 40, 30)
    # saving the same card again replaces its cut-out instead of adding a second one
    r = a.put(f"/api/cutouts/{src}", data={"name": "Роза"}, files={"png": ("cutout.png", png((50, 50)), "image/png")})
    assert r.json()["id"] == first["id"] and r.json()["w"] == 50
    mine = [c for c in a.get("/api/admin/cutouts").json() if c["source"] == src]
    assert len(mine) == 1 and mine[0]["name"] == "Роза"
    full = a.get(mine[0]["png"])
    assert full.headers["content-type"] == "image/png" and Image.open(io.BytesIO(full.content)).size == (50, 50)
    th = a.get(mine[0]["thumb"])
    assert th.status_code == 200 and Image.open(io.BytesIO(th.content)).mode == "RGBA"


def test_upload_rename_delete_and_bad_files():
    a = user_client(admin=True)
    jpg = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(jpg, "JPEG")
    r = a.post("/api/admin/cutouts", files={"file": ("логотип.jpg", jpg.getvalue(), "image/jpeg")})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["name"] == "логотип" and c["source"] is None
    assert Image.open(io.BytesIO(a.get(c["png"]).content)).format == "PNG"  # stored as PNG
    assert a.patch(f"/api/admin/cutouts/{c['id']}", json={"name": "Лого"}).json()["name"] == "Лого"
    assert a.post("/api/admin/cutouts", files={"file": ("x.png", b"not an image", "image/png")}).status_code == 400
    assert a.delete(f"/api/admin/cutouts/{c['id']}").status_code == 204
    assert a.get(c["png"]).status_code == 404


def test_layouts_and_qr_are_admin_only():
    a, u = user_client(admin=True), user_client(admin=False)
    for path in ("/api/admin/cutouts", "/api/admin/print", "/api/admin/print/qr.svg?text=x"):
        assert u.get(path).status_code == 403
    assert u.put("/api/cutouts/c1", data={"name": "x"}, files={"png": ("c.png", png(), "image/png")}).status_code == 403
    assert TestClient(app).get("/api/admin/print").status_code == 401

    booklet = {"t": {"h1": "Котики"}, "slots": [{"k": "item", "img": 5, "name": "Рыжик", "price": "250 ₽"}], "qr": {"max": "https://max.ru/x"}}
    assert a.put("/api/admin/print", json={"booklet": booklet}).status_code == 200
    card = {"t": {"brand1": "3D"}, "img": {"logo": "logo"}}
    got = a.put("/api/admin/print", json={"card": card}).json()
    assert got == {"card": card, "booklet": booklet}  # saving one layout keeps the other
    assert a.get("/api/admin/print").json() == got

    qr = a.get("/api/admin/print/qr.svg", params={"text": "https://3dmew.ru"})
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg+xml") and b"<svg" in qr.content
    assert a.get("/api/admin/print/qr.svg", params={"text": "x", "color": "red"}).status_code == 422


def test_print_page_is_served():
    r = TestClient(app).get("/admin/print")
    assert r.status_code == 200 and "Визитки и буклет" in r.text
