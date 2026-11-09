"""Catalogue previews (the card without the price plate) for products that do not have one yet.

    .venv/bin/python -m tools.make_tiles          # only products without a preview
    .venv/bin/python -m tools.make_tiles --all    # all products again

Works for cards in the builder's main layout. A cleaner preview (only the name, without badges and description)
appears when the card is published again from the builder with the «🛒 Опубликовать» button.
"""
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Item, Product
from app.shop import tile_from_card


def main() -> None:
    every = "--all" in sys.argv
    done = skipped = 0
    with SessionLocal() as db:
        for p in db.execute(select(Product)).scalars():
            if (p.tile and not every) or not p.image:
                continue
            it = db.get(Item, p.item_id) if p.item_id else None
            layout = str(((it.state if it else None) or {}).get("layout") or "")
            t = tile_from_card(p.image, layout)
            if t:
                p.tile = t
                done += 1
            else:
                skipped += 1
        db.commit()
    print(f"Готово: превью сделано для {done} товаров" + (f", пропущено {skipped} (другой макет карточки)" if skipped else ""))


if __name__ == "__main__":
    main()
