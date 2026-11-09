"""Personal account: profile, password, sign out everywhere, deleting the account."""
import uuid

from tests.test_shop import admin_client, client


def test_account_profile_password_delete():
    u = client()
    login = "acc" + uuid.uuid4().hex[:8]
    assert u.post("/api/auth/register", json={"login": login, "password": "секрет123"}).status_code == 200
    assert client().get("/api/account").status_code == 401
    a = u.get("/api/account").json()
    assert a["has_password"] and a["counts"]["orders"] == 0 and not a["admin"]
    assert u.patch("/api/account", json={"email": "плохая почта"}).status_code == 400
    a = u.patch("/api/account", json={"name": "Оля", "phone": "+7 900 000-00-00", "email": "olya@example.ru",
                                      "address": "Москва, ул. Пример, 1", "delivery": "nope"}).json()
    assert a["name"] == "Оля" and a["phone"] and a["delivery"] == "" and a["address"].startswith("Москва")
    assert u.get("/api/me").json()["name"] == "Оля"

    # password: the old one is checked, other devices are signed out
    other = client()
    assert other.post("/api/auth/login", json={"login": login, "password": "секрет123"}).status_code == 200
    assert u.post("/api/account/password", json={"old": "неверный", "new": "новый123"}).status_code == 400
    assert u.post("/api/account/password", json={"old": "секрет123", "new": "новый123"}).status_code == 200
    assert u.get("/api/account").status_code == 200 and other.get("/api/account").status_code == 401
    assert client().post("/api/auth/login", json={"login": login, "password": "новый123"}).status_code == 200

    # delete: needs the word and the password; the admin cannot delete himself here
    assert u.post("/api/account/delete", json={"confirm": "да", "password": "новый123"}).status_code == 400
    assert u.post("/api/account/delete", json={"confirm": "удалить", "password": "x"}).status_code == 400
    assert u.post("/api/account/delete", json={"confirm": "Удалить", "password": "новый123"}).status_code == 200
    assert u.get("/api/account").status_code == 401
    assert client().post("/api/auth/login", json={"login": login, "password": "новый123"}).status_code == 401
    assert admin_client().post("/api/account/delete", json={"confirm": "удалить", "password": "x"}).status_code == 400
