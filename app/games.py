"""«Мяу-аркада»: progress of the games on the server and the leaderboard.

A player is the signed-in account, or (without an account) a random token the browser keeps in localStorage and sends
in the X-Player header; only its SHA-256 is stored. Nothing about the child is collected: only the game progress
and a nickname the player typed himself (optional; without it the player is not shown on the leaderboard).
Signed-in players see the same progress on every device; a guest's progress moves to the account on sign-in."""
import json
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import GamePlayer, GameScore, User
from .security import client_ip, current_admin, current_user_optional, is_admin, rate_limit, sha256

router = APIRouter(prefix="/api/games")

TOKEN = re.compile(r"^[a-f0-9]{32}$")
KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,59}$")
REC = re.compile(r"^rec\.([a-z]{2,15})\.([a-z0-9]{1,15})$")
LOCAL_ONLY = re.compile(r"^(pid|mute|pixel\.p\..*)$")  # device settings and unfinished drawings stay in the browser
GAMES = {"blocks", "snake", "run", "bridge", "fly", "stack", "sort", "mem", "rhythm", "pixel"}
LOWER = {("blocks", "sprint"), ("mem", "s"), ("mem", "m"), ("mem", "l")}  # time: less is better
MAX_DATA = 100_000
MAX_SCORE = 10_000_000
NICK = re.compile(r"^[A-Za-zА-Яа-яЁё0-9 _\-]{2,16}$")
BAD = ("хуй", "хуе", "хуё", "пизд", "ебат", "ебал", "ебан", "ебну", "бляд", "блят", "сука", "суки", "муда", "мудо", "пидор",
       "пидар", "залуп", "шлюх", "гандон", "дерьм", "говн", "жоп", "fuck", "shit", "bitch", "dick", "porn", "nazi", "нацист", "гитлер")


def is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def best(game: str, mode: str, a: Any, b: Any) -> Any:
    """The better of two records; 0 or nothing means «no record yet»."""
    if not is_num(a) or a <= 0:
        return b
    if not is_num(b) or b <= 0:
        return a
    return min(a, b) if (game, mode) in LOWER else max(a, b)


def merge(old: dict, new: dict, fresh: bool) -> dict:
    """Join the server's progress with the browser's.

    Records keep the better value. A fresh browser (first sync, or a guest signing in) can't overwrite progress:
    numbers keep the larger, lists are joined, maps keep the larger value per key. Later syncs send only the keys
    the player just changed, and those win (e.g. «start the snake from level 1 again»)."""
    out = dict(old or {})
    for k, v in (new or {}).items():
        if not isinstance(k, str) or not KEY.fullmatch(k) or LOCAL_ONLY.fullmatch(k):
            continue
        o = out.get(k)
        m = REC.fullmatch(k)
        if m:
            if is_num(v):
                out[k] = best(m.group(1), m.group(2), o, v)
            continue
        if o is None:
            out[k] = v
        elif isinstance(v, list) and isinstance(o, list):
            out[k] = (o + [x for x in v if x not in o])[-500:] if fresh else v[-500:]
        elif isinstance(v, dict) and isinstance(o, dict):
            d = dict(o)
            for kk, vv in v.items():
                ov = d.get(kk)
                d[kk] = max(ov, vv) if fresh and is_num(ov) and is_num(vv) else (ov if fresh and ov is not None else vv)
            out[k] = d
        elif fresh:
            if is_num(v) and is_num(o):
                out[k] = max(o, v)
        else:
            out[k] = v
    return out


def boards(data: dict) -> dict[tuple[str, str], int]:
    """Leaderboard rows of one player, taken from his progress."""
    out: dict[tuple[str, str], int] = {}
    for k, v in data.items():
        m = REC.fullmatch(k)
        if m and m.group(1) in GAMES and m.group(1) != "pixel" and is_num(v) and 0 < v <= MAX_SCORE:
            out[(m.group(1), m.group(2))] = int(round(v))
    done = data.get("pixel.done")
    if isinstance(done, list) and done:
        out[("pixel", "all")] = len(done)
    stars = data.get("bridge.stars")
    if isinstance(stars, dict):
        n = sum(int(v) for v in stars.values() if is_num(v) and 0 < v <= 3)
        if n:
            out[("bridge", "stars")] = n
    return out


def save_scores(db: Session, p: GamePlayer) -> None:
    db.execute(delete(GameScore).where(GameScore.player_id == p.id))
    for (game, mode), score in boards(p.data or {}).items():
        db.add(GameScore(player_id=p.id, game=game, mode=mode, score=score))


def player(request: Request, db: Session, user: Optional[User], create: bool) -> Optional[GamePlayer]:
    token = request.headers.get("x-player", "")
    th = sha256(token) if TOKEN.fullmatch(token) else None
    guest = db.execute(select(GamePlayer).where(GamePlayer.token_hash == th)).scalar_one_or_none() if th else None
    if user is None:
        if guest is None and create:
            if not th:
                raise HTTPException(400, "Нет номера игрока")
            guest = GamePlayer(token_hash=th, data={})
            db.add(guest)
            db.flush()
        return guest
    p = db.execute(select(GamePlayer).where(GamePlayer.user_id == user.id)).scalar_one_or_none()
    if guest is not None and guest.user_id is None:
        if p is None:  # the guest signed in: his progress becomes the account's
            guest.user_id = user.id
            p = guest
        else:  # the account already plays elsewhere: add this browser's progress to it
            p.data = merge(p.data, guest.data, fresh=True)
            p.nick = p.nick or guest.nick
            db.delete(guest)
            db.flush()
            save_scores(db, p)
    if p is None and create:
        p = GamePlayer(user_id=user.id, data={})
        db.add(p)
        db.flush()
    return p


def me_out(p: Optional[GamePlayer], user: Optional[User]) -> dict:
    return {"nick": p.nick if p else "", "data": (p.data if p else None) or {}, "signed_in": user is not None,
            "name": user.name if user else ""}


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(current_user_optional)):
    p = player(request, db, user, create=False)
    db.commit()
    return me_out(p, user)


class SyncIn(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    fresh: bool = False  # the browser sends everything it has (first sync), not just what changed


@router.put("/me")
def sync(body: SyncIn, request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(current_user_optional)):
    rate_limit("games:" + client_ip(request), 120, 60)
    if len(json.dumps(body.data, ensure_ascii=False)) > MAX_DATA:
        raise HTTPException(413, "Слишком много данных")
    p = player(request, db, user, create=True)
    merged = merge(p.data, body.data, fresh=body.fresh)
    if len(json.dumps(merged, ensure_ascii=False)) <= MAX_DATA:
        p.data = merged
    save_scores(db, p)
    db.commit()
    return me_out(p, user)


class NickIn(BaseModel):
    nick: str = Field(default="", max_length=40)


def clean_nick(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    if not s:
        return ""
    if not NICK.fullmatch(s):
        raise HTTPException(400, "Ник: от 2 до 16 букв или цифр")
    flat = re.sub(r"[^a-zа-я]", "", s.lower().replace("ё", "е"))
    if any(w.replace("ё", "е") in flat for w in BAD):
        raise HTTPException(400, "Такой ник не подойдёт, придумай другой")
    return s


@router.put("/nick")
def set_nick(body: NickIn, request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(current_user_optional)):
    rate_limit("games-nick:" + client_ip(request), 20, 600)
    nick = clean_nick(body.nick)
    p = player(request, db, user, create=True)
    if nick and db.execute(select(GamePlayer.id).where(func.lower(GamePlayer.nick) == nick.lower(), GamePlayer.id != p.id)).first():
        raise HTTPException(409, "Такой ник уже занят")
    p.nick = nick
    db.commit()
    return me_out(p, user)


@router.get("/top")
def top(request: Request, game: str = Query(pattern=r"^[a-z]{2,15}$"), mode: str = Query(pattern=r"^[a-z0-9]{1,15}$"),
        limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: Optional[User] = Depends(current_user_optional)):
    lower = (game, mode) in LOWER
    order = GameScore.score.asc() if lower else GameScore.score.desc()
    rows = db.execute(select(GameScore.score, GamePlayer.id, GamePlayer.nick)
                      .join(GamePlayer, GamePlayer.id == GameScore.player_id)
                      .where(GameScore.game == game, GameScore.mode == mode, GamePlayer.nick != "")
                      .order_by(order, GameScore.updated_at).limit(limit)).all()
    p = player(request, db, user, create=False)
    admin = is_admin(user)
    items = [{"place": i + 1, "nick": r.nick, "score": r.score, "me": bool(p and r.id == p.id)} | ({"pid": r.id} if admin else {})
             for i, r in enumerate(rows)]
    me = None
    mine = db.execute(select(GameScore.score).where(GameScore.player_id == p.id, GameScore.game == game,
                                                    GameScore.mode == mode)).scalar() if p else None
    if mine is not None:
        better = GameScore.score < mine if lower else GameScore.score > mine
        ahead = db.execute(select(func.count()).select_from(GameScore).join(GamePlayer, GamePlayer.id == GameScore.player_id)
                           .where(GameScore.game == game, GameScore.mode == mode, GamePlayer.nick != "", better)).scalar()
        me = {"place": ahead + 1, "score": mine, "listed": bool(p.nick)}
    total = db.execute(select(func.count()).select_from(GameScore).join(GamePlayer, GamePlayer.id == GameScore.player_id)
                       .where(GameScore.game == game, GameScore.mode == mode, GamePlayer.nick != "")).scalar()
    db.commit()
    return {"game": game, "mode": mode, "lower": lower, "items": items, "me": me, "total": total}


@router.delete("/admin/players/{pid}/nick", status_code=204)
def hide_nick(pid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    """The admin removes a rude nickname: the player disappears from the leaderboard until he picks another one."""
    p = db.get(GamePlayer, pid)
    if p:
        p.nick = ""
        db.commit()
    return Response(status_code=204)
