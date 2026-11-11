"""Admin → «Библиотека»: uploads, and pictures kept elsewhere on the site listed in one place."""
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


def ip() -> dict:
    # every test client looks like a separate visitor, so the sign-up rate limit doesn't kick in
    return {"x-forwarded-for": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}


def user_client(admin: bool) -> TestClient:
    c = TestClient(app, headers=ip())
    r = c.post("/api/auth/register", json={"login": "Библ " + uuid.uuid4().hex[:8], "password": "секрет123"})
    assert r.status_code == 200, r.text
    if admin:
        with SessionLocal() as db:
            db.execute(update(User).where(User.id == r.json()["id"]).values(is_admin=True))
            db.commit()
    return c


def keys(c: TestClient) -> dict:
    r = c.get("/api/admin/library")
    assert r.status_code == 200, r.text
    return {e["key"]: e for e in r.json()["items"]}


def test_upload_list_rename_delete():
    a = user_client(admin=True)
    video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
    r = a.post("/api/admin/library", files=[("files", ("кот.png", png(), "image/png")),
                                            ("files", ("ролик.mp4", video, "video/mp4"))])
    assert r.status_code == 200, r.text
    pic, vid = r.json()["items"]
    assert (pic["kind"], pic["mime"], pic["w"], pic["h"], pic["src"]) == ("image", "image/png", 40, 30, "upload")
    assert vid["kind"] == "video" and vid["thumb"] is None

    lib = keys(a)
    assert pic["key"] in lib and vid["key"] in lib and lib[pic["key"]]["del"]
    full = a.get(pic["url"])  # the original is kept as is: PNG keeps its transparency
    assert full.headers["content-type"] == "image/png" and Image.open(io.BytesIO(full.content)).mode == "RGBA"
    assert Image.open(io.BytesIO(a.get(pic["thumb"]).content)).format == "JPEG"
    part = a.get(vid["url"], headers={"range": "bytes=0-9"})
    assert part.status_code == 206 and len(part.content) == 10

    fid = pic["key"].split("-")[1]
    assert a.patch(f"/api/admin/library/files/{fid}", json={"name": "Рыжик"}).json()["name"] == "Рыжик"
    assert a.delete(f"/api/admin/library/files/{fid}").status_code == 204
    assert a.get(pic["url"]).status_code == 404 and pic["key"] not in keys(a)


def test_bad_files_are_refused():
    a = user_client(admin=True)
    assert a.post("/api/admin/library", files={"files": ("x.png", b"not an image", "image/png")}).status_code == 400
    assert a.post("/api/admin/library", files={"files": ("model.stl", b"solid x", "application/sla")}).status_code == 400


def test_lists_cutouts_and_builder_cards():
    a = user_client(admin=True)
    src = "c" + uuid.uuid4().hex[:10]
    cut = a.put(f"/api/cutouts/{src}", data={"name": "Без фона"}, files={"png": ("c.png", png(), "image/png")}).json()
    assert a.put(f"/api/items/{src}", json={"kind": "card", "title": "Карточка", "thumb": "data:image/jpeg;base64,AA", "t": 1}).status_code == 200
    assert a.put(f"/api/blobs/{src}", files={"png": ("card.png", png((30, 40)), "image/png")}).status_code == 200
    # a photo uploaded in the builder (its row is read as «t», which is also a property of SQLAlchemy rows)
    ph = "p" + uuid.uuid4().hex[:10]
    assert a.put(f"/api/photos/{ph}", json={"name": "кот.jpg", "size": 123, "thumb": "data:image/jpeg;base64,AA", "t": 1762800000000}).status_code == 200
    assert a.put(f"/api/blobs/{ph}", files={"photo": ("кот.png", png(), "image/png")}).status_code == 200
    lib = keys(a)
    assert lib[f"photo-{ph}"]["src"] == "photo" and lib[f"photo-{ph}"]["t"].startswith("2025-11-10")
    assert a.get(lib[f"photo-{ph}"]["url"]).status_code == 200
    assert lib[f"cut-{cut['id']}"]["src"] == "cutout"
    card = lib[f"card-{src}"]
    assert card["src"] == "card" and card["name"] == "Карточка"
    assert a.get(card["url"]).status_code == 200


def test_admin_only():
    u = user_client(admin=False)
    assert u.get("/api/admin/library").status_code == 403
    assert u.post("/api/admin/library", files={"files": ("a.png", png(), "image/png")}).status_code == 403
    assert TestClient(app, headers=ip()).get("/api/admin/library").status_code == 401


def test_delete_from_any_place():
    a = user_client(admin=True)
    src = "d" + uuid.uuid4().hex[:10]
    cut = a.put(f"/api/cutouts/{src}", data={"name": "Без фона"}, files={"png": ("c.png", png(), "image/png")}).json()
    a.put(f"/api/items/{src}", json={"kind": "card", "title": "Карточка", "thumb": "data:image/jpeg;base64,AA", "t": 1})
    a.put(f"/api/blobs/{src}", files={"png": ("card.png", png(), "image/png")})
    ph = "q" + uuid.uuid4().hex[:10]
    a.put(f"/api/photos/{ph}", json={"name": "кот.jpg", "size": 1, "thumb": "data:image/jpeg;base64,AA", "t": 1})
    a.put(f"/api/blobs/{ph}", files={"photo": ("кот.png", png(), "image/png")})
    up = a.post("/api/admin/library", files={"files": ("a.png", png(), "image/png")}).json()["items"][0]
    want = [up["key"], f"cut-{cut['id']}", f"card-{src}", f"photo-{ph}"]
    lib = keys(a)
    assert all(lib[k]["del"] for k in want)
    r = a.post("/api/admin/library/delete", json={"keys": want + ["prod-1", "zzz-1"]}).json()
    assert sorted(r["deleted"]) == sorted(want)
    assert {x["key"] for x in r["skipped"]} == {"prod-1", "zzz-1"}
    lib = keys(a)
    assert not any(k in lib for k in want)
    assert a.get(f"/api/items/{src}").status_code == 404
    assert user_client(admin=False).post("/api/admin/library/delete", json={"keys": ["up-1"]}).status_code == 403


def test_categories():
    a = user_client(admin=True)
    one = a.post("/api/admin/library", data={"category": "Фото пластика"},
                 files={"files": ("катушка.png", png(), "image/png")}).json()["items"][0]
    assert one["cat"] == "Фото пластика"
    two = a.post("/api/admin/library", files={"files": ("x.png", png(), "image/png")}).json()["items"][0]
    assert two["cat"] == ""
    fid = two["key"].split("-")[1]
    assert a.patch(f"/api/admin/library/files/{fid}", json={"category": "Мои фоны"}).json()["cat"] == "Мои фоны"
    r = a.post("/api/admin/library/category", json={"keys": [one["key"], two["key"], "pm-1"], "category": "Логотипы"}).json()
    assert (r["updated"], r["skipped"]) == (2, 1)
    lib = a.get("/api/admin/library").json()
    items = {e["key"]: e for e in lib["items"]}
    assert items[one["key"]]["cat"] == items[two["key"]]["cat"] == "Логотипы"
    assert "Фото пластика" in lib["categories"]
    assert a.patch(f"/api/admin/library/files/{fid}", json={"name": "Новое"}).json()["cat"] == "Логотипы"  # rename keeps it
