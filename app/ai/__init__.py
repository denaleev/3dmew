"""Server-side AI: recognise what is on the photo (CLIP) and write simple texts (Claude, optional)."""
import base64
import io
import json
import logging
import re
import threading
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from PIL import Image
from pydantic import BaseModel, Field

from ..config import settings
from ..models import User
from ..security import client_ip, current_user_optional, rate_limit
from .categories import CATEGORIES

router = APIRouter(prefix="/api/ai")
log = logging.getLogger("kartochki.ai")
_lock = threading.Lock()
_clip = None
_emb = None

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)


def _load():
    global _clip, _emb
    with _lock:
        if _clip is None:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            _clip = ort.InferenceSession(str(settings.MODELS_DIR / "clip_visual.onnx"), opts, providers=["CPUExecutionProvider"])
            _emb = np.load(settings.MODELS_DIR / "categories.npy")
            if _emb.shape[0] != len(CATEGORIES):
                raise RuntimeError("categories.npy does not match categories.py: run python -m tools.build_categories")
    return _clip, _emb


def ai_ready() -> bool:
    return (settings.MODELS_DIR / "clip_visual.onnx").exists() and (settings.MODELS_DIR / "categories.npy").exists()


def recognize(img: Image.Image, top: int = 3) -> list[dict]:
    """Top guesses of what the 3D-printed item is."""
    sess, emb = _load()
    img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, "white")
    img = Image.alpha_composite(bg, img).convert("RGB")
    side = max(img.size)
    sq = Image.new("RGB", (side, side), "white")
    sq.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    x = (np.asarray(sq.resize((224, 224), Image.BICUBIC), np.float32) / 255 - MEAN) / STD
    v = sess.run(None, {"pixel_values": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    v /= np.linalg.norm(v)
    logits = 100 * emb @ v
    p = np.exp(logits - logits.max())
    p /= p.sum()
    out = []
    for i in np.argsort(-p)[:top]:
        if out and p[i] < 0.04:
            break
        name, g, _, kid = CATEGORIES[i]
        out.append({"name": name, "g": g, "kid": kid, "p": round(float(p[i]), 3)})
    return out


KIDS = """Пиши просто и понятно, как для ребёнка 8–10 лет: короткие предложения, обычные слова. Без канцелярита и сложных терминов: не пиши «данный», «является», «изделие», «обладает», «идеально подходит».
Название: что это за предмет (как его назовёт ребёнок) и цвет, до 60 символов. Слово «изделие» не используй.
Описание: 2–3 коротких предложения: что это, чем нравится, кому подарить.
Характеристики: 4–5 строк «Ключ: значение» простыми словами."""


def claude_text(img_b64: str, data: "FillIn", hint: Optional[str]) -> Optional[dict]:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=60.0, max_retries=2)
    prompt = f"""Ты помогаешь ребёнку сделать карточку товара для маркетплейса. Товар напечатан на 3D-принтере (фото приложено).
Посмотри на фото и определи, что это за предмет.{f' Нейросеть-помощник думает, что это: {hint}.' if hint else ''}
Данные продавца (могут быть пустыми):
Название: {data.title}
Описание: {data.description}
Характеристики:
{data.features}
{KIDS}
Сохрани факты продавца (материал, размеры), размеры не выдумывай. Цвет определи по фото.
Ответь только JSON без пояснений: {{"object":"что это, 1–3 слова","gender":"m|f|n|pl","title":"...","description":"...","features":["Ключ: значение"]}}"""
    resp = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": prompt},
        ]}],
    )
    if resp.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    o = json.loads(m.group(0))
    feats = [str(f)[:120] for f in (o.get("features") or []) if isinstance(f, (str, int, float))][:8]
    return {"object": str(o.get("object") or "")[:60], "gender": str(o.get("gender") or "m")[:2],
            "title": str(o.get("title") or "")[:120], "description": str(o.get("description") or "")[:1200], "features": feats}


class Guess(BaseModel):
    name: str = Field(max_length=80)
    g: str = Field(default="m", max_length=2)
    kid: Optional[str] = Field(default=None, max_length=300)
    p: Optional[float] = None


class FillIn(BaseModel):
    fields: list[str] = Field(default_factory=lambda: ["title", "desc", "feats"], max_length=3)
    image: Optional[str] = Field(default=None, max_length=8_000_000)  # base64 JPEG of the cut-out item
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=5000)
    features: str = Field(default="", max_length=5000)
    guess: Optional[Guess] = None


@router.post("/fill")
def fill(data: FillIn, request: Request, user: Optional[User] = Depends(current_user_optional)):
    rate_limit("fill:" + (user.id if user else client_ip(request)), settings.AI_FILLS_PER_HOUR, 3600)
    if not data.image:
        raise HTTPException(400, "Нет фото")
    try:
        img = Image.open(io.BytesIO(base64.b64decode(data.image, validate=True)))
        img.load()
    except Exception:
        raise HTTPException(400, "Не получилось открыть фото")
    guesses: list[dict] = []
    if ai_ready():
        try:
            guesses = recognize(img)
        except Exception as e:
            log.exception("recognition failed: %s", e)
    if data.guess:  # the child picked the right answer: put it first
        guesses = [data.guess.model_dump()] + [g for g in guesses if g["name"] != data.guess.name]
    text, engine = None, "clip" if guesses else "none"
    if settings.ANTHROPIC_API_KEY:
        try:
            text = claude_text(data.image, data, guesses[0]["name"] if guesses else None)
            if text:
                engine = "claude"
                if text.get("object") and not data.guess and not any(g["name"] == text["object"] for g in guesses):
                    guesses = [{"name": text["object"], "g": text.get("gender", "m"), "kid": None, "p": None}] + guesses[:2]
        except Exception as e:
            log.warning("claude failed: %s", e)
    return {"guesses": guesses, "text": text, "engine": engine}


@router.get("/status")
def status():
    return {"recognition": ai_ready(), "claude": bool(settings.ANTHROPIC_API_KEY)}
