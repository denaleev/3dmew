"""Import the ready-made cards from seed/cards.json into the builder library of an account and into the shop.

    .venv/bin/python -m tools.import_cards denis            # library + shop (shown at once)
    .venv/bin/python -m tools.import_cards denis --hidden   # library + shop, hidden until you check them

Running it again does not create duplicates: cards with the same title in the library are skipped.
"""
import json
import secrets
import sys
import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import BlobSet, Item, Product, ProductMedia, User
from app.shop import jpeg, tile_from_card

SEED = Path(__file__).resolve().parent.parent / "seed"


def thumb_url(data: bytes) -> str:
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(jpeg(data, 360, 80)).decode()


def item_photo(card: bytes) -> bytes:
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(card)).convert("RGB")
    w, h = im.size
    out = io.BytesIO()
    im.crop((int(w * .16), int(h * .2), w, int(h * .82))).save(out, "JPEG", quality=92)
    return out.getvalue()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Укажи логин администратора: python -m tools.import_cards denis")
    login, hidden = sys.argv[1].strip().lower(), "--hidden" in sys.argv
    cards = json.loads((SEED / "cards.json").read_text("utf-8"))
    with SessionLocal() as db:
        u = db.execute(select(User).where(User.login == login)).scalar_one_or_none()
        if not u:
            sys.exit(f"Аккаунт «{login}» не найден. Сначала зарегистрируйся на сайте.")
        have = set(db.execute(select(Item.title).where(Item.user_id == u.id, Item.kind == "card")).scalars())
        added = 0
        for c in cards:
            if c["title"] in have:
                print(f"  пропускаю «{c['title']}»: уже есть в библиотеке")
                continue
            imgs = [(SEED / "cards" / n).read_bytes() for n in c["images"]]
            iid = secrets.token_hex(10)
            mat = next((ln.split(":", 1)[1].strip() for ln in c["feats"].splitlines()
                        if ln.lower().startswith("материал:")), "PLA")
            state = {"title": c["title"], "desc": c["desc"], "feats": c["feats"], "price": str(c["price"]), "old": "",
                     "shopCat": c["cat"], "calcMat": mat, "b3d": True, "bHit": bool(c.get("hit")),
                     "bNew": bool(c.get("new")), "bHand": bool(c.get("hand")), "bCustom": "", "rating": "",
                     "reviews": ""}
            db.add(Item(id=iid, user_id=u.id, kind="card", title=c["title"], thumb=thumb_url(imgs[0]), state=state,
                        t=int(time.time() * 1000)))
            db.flush()
            # the photo of the item, cut from the middle of the card: the builder removes its background itself
            db.add(BlobSet(id=iid, user_id=u.id, png=imgs[0], photo=item_photo(imgs[0]), photo_type="image/jpeg",
                           product_cut=True))
            p = Product(item_id=iid, title=c["title"], description=c["desc"], features=c["feats"], category=c["cat"],
                        price=Decimal(str(c["price"])), material=mat, stock=0, published=not hidden,
                        sort=c.get("sort", 0), views=0, print_minutes=0, grams=0,
                        image=jpeg(imgs[0], 1600, 88), thumb=jpeg(imgs[0], 520, 82), tile=tile_from_card(imgs[0]))
            db.add(p)
            db.flush()
            for i, data in enumerate(imgs[1:], 1):
                big = jpeg(data, 1800, 88)
                db.add(ProductMedia(product_id=p.id, kind="image", mime="image/jpeg", name=f"фото {i}", size=len(big),
                                    data=big, thumb=jpeg(data, 400, 82), sort=i))
            added += 1
            print(f"  + {c['title']} — {c['price']} ₽ ({c['cat']})")
        db.commit()
    print(f"Готово: добавлено {added} из {len(cards)}." + (" Товары скрыты: включи их на витрине." if hidden else ""))


if __name__ == "__main__":
    main()
