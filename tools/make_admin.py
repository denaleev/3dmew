"""Make an existing account a shop administrator (or take the right away).

    .venv/bin/python -m tools.make_admin denis
    .venv/bin/python -m tools.make_admin denis --off
"""
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Укажи имя (логин) аккаунта: python -m tools.make_admin denis")
    login, on = sys.argv[1].strip().lower(), "--off" not in sys.argv
    with SessionLocal() as db:
        u = db.execute(select(User).where(User.login == login)).scalar_one_or_none()
        if not u:
            sys.exit(f"Аккаунт «{login}» не найден. Сначала зарегистрируйся на сайте.")
        u.is_admin = on
        db.commit()
        print(f"{u.name}: {'теперь администратор' if on else 'больше не администратор'}")


if __name__ == "__main__":
    main()
