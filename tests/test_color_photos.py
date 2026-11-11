"""Photos of a product printed in different plastics, and the note shown on the product page."""
import uuid

from tests.test_shop import admin_client, client, png_bytes, publish


def test_photos_by_colour_and_note():
    a = admin_client()
    _, pub = publish(a, title="Тыква " + uuid.uuid4().hex[:5], extra={"shopNote": "Шарнирная: лапки двигаются"})
    pid = pub["id"]
    red = a.post("/api/admin/colors", data={"name": "Красный " + uuid.uuid4().hex[:4], "hex": "#ff0000"}).json()
    blue = a.post("/api/admin/colors", data={"name": "Синий " + uuid.uuid4().hex[:4], "hex": "#0000ff"}).json()

    # a photo uploaded for the red colour, and a general one
    media = a.post(f"/api/admin/products/{pid}/media", data={"color_id": str(red["id"])},
                   files={"files": ("red.png", png_bytes(), "image/png")}).json()["media"]
    assert media[-1]["color_id"] == red["id"]
    media = a.post(f"/api/admin/products/{pid}/media", files={"files": ("any.png", png_bytes(), "image/png")}).json()["media"]
    general = media[-1]
    assert general["color_id"] is None
    # the colour of a photo can be changed and removed; an unknown colour means «no colour»
    assert a.patch(f"/api/admin/products/{pid}/media/{general['id']}", json={"color_id": blue["id"]}).json()["color_id"] == blue["id"]
    assert a.patch(f"/api/admin/products/{pid}/media/{general['id']}", json={"color_id": 99999999}).json()["color_id"] is None
    assert client().patch(f"/api/admin/products/{pid}/media/{general['id']}", json={"color_id": None}).status_code == 401

    p = client().get(f"/api/shop/products/{pid}").json()
    assert {m["color_id"] for m in p["media"]} == {red["id"], None}
    assert p["note"] == "Шарнирная: лапки двигаются"
    assert a.patch(f"/api/admin/products/{pid}", json={"note": "  Новое примечание "}).status_code == 200
    assert client().get(f"/api/shop/products/{pid}").json()["note"] == "Новое примечание"
