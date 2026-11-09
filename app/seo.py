"""Link previews: Telegram, MAX, VK, WhatsApp and search engines read <meta property="og:…"> from the HTML.
They do not run JavaScript, so the tags are put into the page on the server."""
import html

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Product
from .shop import shop_info, stamp

router = APIRouter(include_in_schema=False)


def meta_tags(title: str, desc: str, image: str, url: str, site: str, kind: str = "website") -> str:
    e = lambda s: html.escape(" ".join(str(s or "").split()), quote=True)  # noqa: E731
    return (f'<meta name="description" content="{e(desc)}">\n'
            f'<meta property="og:type" content="{kind}">\n<meta property="og:site_name" content="{e(site)}">\n'
            f'<meta property="og:title" content="{e(title)}">\n<meta property="og:description" content="{e(desc)}">\n'
            f'<meta property="og:url" content="{e(url)}">\n<meta property="og:image" content="{e(image)}">\n'
            f'<meta property="og:locale" content="ru_RU">\n<meta name="twitter:card" content="summary">\n')


def shop_page(db: Session, title: str, desc: str, image: str, url: str, kind: str = "website") -> HTMLResponse:
    s = shop_info(db)
    page = (settings.STATIC_DIR / "shop.html").read_text("utf-8")
    page = page.replace("<title>3DМяу</title>",
                        f"<title>{html.escape(title)}</title>\n" + meta_tags(title, desc, image, url, s["name"], kind), 1)
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


def short(text: str, n: int = 200) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


@router.api_route("/", methods=["GET", "HEAD"])
def storefront(db: Session = Depends(get_db)):
    """The shop for customers, with the preview tags for messengers."""
    s = shop_info(db)
    desc = s.get("meta_description") or s.get("tagline") or ""
    title = s["name"] + (" — " + s["tagline"] if s.get("tagline") else "")
    return shop_page(db, short(title, 90), short(desc), f"{settings.PUBLIC_URL}/img/logo-512.png", settings.PUBLIC_URL + "/")


@router.api_route("/p/{pid}", methods=["GET", "HEAD"])
def product_link(pid: int, db: Session = Depends(get_db)):
    """A link to one product for sharing: the preview shows its photo, name and price, then the shop opens it."""
    p = db.get(Product, pid)
    if not p or not p.published:
        return storefront(db)
    price = f"{float(p.price):,.0f}".replace(",", " ") + " ₽"
    resp = shop_page(db, f"{p.title} — {price}", short(p.description or p.category or ""),
                     f"{settings.PUBLIC_URL}/api/shop/products/{p.id}/image?v={stamp(p.updated_at)}",
                     f"{settings.PUBLIC_URL}/p/{p.id}", "product")
    # the shop opens products by #product/ID
    body = resp.body.decode().replace("<head>", f"<head>\n<script>location.replace('/#product/{p.id}')</script>", 1)
    return HTMLResponse(body, headers={"Cache-Control": "no-cache"})
