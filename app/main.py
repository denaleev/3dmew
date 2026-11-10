"""Конструктор карточек: web server.

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import account, admin, ai, auth, catalog, games, library, maxbot, printing, seo, shop, social, store
from .config import settings
from .db import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="Магазин 3D-печати", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(store.router)
app.include_router(ai.router)
app.include_router(social.public)  # before shop: /products/{pid}/reviews must win over /products/{pid}/{kind}
app.include_router(social.admin)
app.include_router(shop.router)
app.include_router(admin.router)
app.include_router(catalog.public)
app.include_router(catalog.admin)
app.include_router(maxbot.router)
app.include_router(printing.router)
app.include_router(library.router)
app.include_router(games.router)
app.include_router(seo.router)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.get("/api/health")
def health():
    with engine.connect() as c:
        c.execute(text("select 1"))
    return {"ok": True, "ai": ai.ai_ready(), "claude": bool(settings.ANTHROPIC_API_KEY)}


class CachedStatic(StaticFiles):
    """Neural network files never change between releases: let browsers keep them."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            resp.headers["Cache-Control"] = "public, max-age=2592000"
        return resp


app.mount("/ai", CachedStatic(directory=settings.STATIC_DIR / "ai"), name="ai")
app.mount("/img", CachedStatic(directory=settings.STATIC_DIR / "img"), name="img")
app.mount("/js", StaticFiles(directory=settings.STATIC_DIR / "js"), name="js")
app.mount("/games", StaticFiles(directory=settings.STATIC_DIR / "games"), name="games")


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/api/shop/favicon/64.png")


def page(name: str):
    return FileResponse(settings.STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


@app.get("/builder")
def builder():
    """The card builder (with the cost calculator and the «publish in shop» button)."""
    return page("index.html")


@app.get("/igry")
def games_page():
    """«Мяу-аркада»: мини-игры для детей. Без рекламы и покупок; прогресс и турнирная таблица на сервере (app/games.py)."""
    return page("igry.html")


@app.get("/admin")
def admin_page():
    """Orders, custom requests, statistics and settings of the shop."""
    return page("admin.html")


@app.get("/admin/print")
def print_page():
    """Business card and booklet builder (admin only: the page asks the API, which checks the account)."""
    return page("print.html")


@app.exception_handler(404)
async def not_found(request, exc):
    detail = getattr(exc, "detail", None) or "Не найдено"
    return JSONResponse({"detail": detail}, status_code=404)
