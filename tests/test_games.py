"""«Мяу-аркада»: progress on the server, moving a guest's progress to the account, the leaderboard."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db import SessionLocal
from app.main import app
from app.models import User


def ip() -> dict:
    return {"x-forwarded-for": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}


def guest() -> TestClient:
    return TestClient(app, headers={**ip(), "x-player": uuid.uuid4().hex})


def signed(c: TestClient | None = None, admin: bool = False) -> TestClient:
    c = c or TestClient(app, headers=ip())
    r = c.post("/api/auth/register", json={"login": "Игрок " + uuid.uuid4().hex[:8], "password": "секрет123"})
    assert r.status_code == 200, r.text
    if admin:
        with SessionLocal() as db:
            db.execute(update(User).where(User.id == r.json()["id"]).values(is_admin=True))
            db.commit()
    return c


def test_guest_progress_is_kept_and_merged():
    g = guest()
    assert g.get("/api/games/me").json()["data"] == {}
    d = {"rec.mem.s": 40, "rec.run.run": 800, "sort.lvl.normal": 5, "mute": True, "pixel.p.cat.s": [1, 2]}
    out = g.put("/api/games/me", json={"data": d, "fresh": True}).json()["data"]
    assert out == {"rec.mem.s": 40, "rec.run.run": 800, "sort.lvl.normal": 5}  # device settings stay in the browser
    # an old record does not overwrite a better one; a time record is better when lower
    out = g.put("/api/games/me", json={"data": {"rec.mem.s": 55, "rec.run.run": 900}}).json()["data"]
    assert out["rec.mem.s"] == 40 and out["rec.run.run"] == 900
    # a fresh browser can't lower the level; a change the player just made can
    assert g.put("/api/games/me", json={"data": {"sort.lvl.normal": 2}, "fresh": True}).json()["data"]["sort.lvl.normal"] == 5
    assert g.put("/api/games/me", json={"data": {"sort.lvl.normal": 2}}).json()["data"]["sort.lvl.normal"] == 2
    assert TestClient(app, headers=ip()).put("/api/games/me", json={"data": {}}).status_code == 400  # no token, no account


def test_guest_progress_moves_to_account_on_sign_in():
    c = guest()
    c.put("/api/games/me", json={"data": {"rec.fly.normal": 12}, "fresh": True})
    signed(c)
    me = c.get("/api/games/me").json()
    assert me["signed_in"] and me["data"]["rec.fly.normal"] == 12
    # another device of the same account sees the same progress
    other = TestClient(app, headers=ip())
    other.cookies.update(c.cookies)
    assert other.get("/api/games/me").json()["data"]["rec.fly.normal"] == 12


def test_leaderboard_shows_only_players_with_nick():
    game_mode = {"game": "stack", "mode": "classic"}
    a, b, c = guest(), guest(), guest()
    nick = "Кот" + uuid.uuid4().hex[:6]
    assert a.put("/api/games/nick", json={"nick": nick}).status_code == 200
    a.put("/api/games/me", json={"data": {"rec.stack.classic": 9_000_001}, "fresh": True})
    b.put("/api/games/me", json={"data": {"rec.stack.classic": 9_000_002}, "fresh": True})  # no nick: not listed
    top = a.get("/api/games/top", params=game_mode).json()
    assert top["items"][0]["nick"] == nick and top["items"][0]["me"]
    assert top["me"]["place"] == 1 and top["me"]["listed"]
    assert b.get("/api/games/top", params=game_mode).json()["me"]["place"] == 1  # his place, though he is not listed
    assert c.put("/api/games/nick", json={"nick": nick.upper()}).status_code == 409  # taken
    assert c.put("/api/games/nick", json={"nick": "x"}).status_code == 400
    assert c.put("/api/games/nick", json={"nick": "сука123"}).status_code == 400
    assert "pid" not in top["items"][0]


def test_lower_is_better_and_admin_hides_nick():
    a, b = guest(), guest()
    n1, n2 = "Быстрый" + uuid.uuid4().hex[:5], "Медленный" + uuid.uuid4().hex[:5]
    a.put("/api/games/nick", json={"nick": n1})
    b.put("/api/games/nick", json={"nick": n2})
    a.put("/api/games/me", json={"data": {"rec.mem.l": 1}, "fresh": True})
    b.put("/api/games/me", json={"data": {"rec.mem.l": 2}, "fresh": True})
    adm = signed(admin=True)
    items = adm.get("/api/games/top", params={"game": "mem", "mode": "l"}).json()["items"]
    assert [i["nick"] for i in items[:2]] == [n1, n2]
    assert adm.delete(f"/api/games/admin/players/{items[0]['pid']}/nick").status_code == 204
    left = [i["nick"] for i in adm.get("/api/games/top", params={"game": "mem", "mode": "l"}).json()["items"]]
    assert n1 not in left and n2 in left
    assert a.delete(f"/api/games/admin/players/{items[1]['pid']}/nick").status_code == 401
