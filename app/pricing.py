"""Cost and price of one printed piece.

The same formula lives in the builder (static/index.html, function calcPrice), so the numbers match.
Everything is per ONE piece. If several pieces are printed on one plate, plastic and time of the
plate are divided by the number of pieces.

    g   = plate grams / pieces                       plastic for one piece, g
    t   = plate hours / pieces                       printer time for one piece, h
    M   = g × (1 + waste%) × plastic price per kg / 1000          plastic
    E   = printer power kW × t × electricity price per kWh        electricity
    A   = t × (printer price / printer life hours + upkeep per h) wear of the printer
    P   = (M + E + A) / (1 − failed prints%)                      printing incl. failed prints
    L   = (setup minutes / pieces + finishing minutes) / 60 × labour per hour
    C   = P + L + packaging + extras                              COST of one piece
    raw = C × (1 + markup%) / (1 − tax% − commission%)
    price = raw rounded up to a "nice" price (…9, …40/…90, …90)
    profit = price × (1 − tax% − commission%) − C
"""
from __future__ import annotations

import math
from typing import Any

DEFAULTS: dict[str, Any] = {
    "materials": {  # ₽ per kg of filament
        "PLA": 1600, "PLA Matte": 1800, "Silk PLA": 2000, "PETG": 1700, "ABS": 1600, "TPU": 2600,
    },
    "waste_pct": 5,          # purge, brim, supports that can't be weighed by the slicer
    "power_w": 150,          # average printer draw while printing
    "kwh_price": 6.5,        # ₽ per kWh
    "printer_price": 70000,  # ₽
    "printer_life_h": 5000,  # hours until the printer is "paid off"
    "upkeep_per_h": 5,       # ₽ per hour: nozzles, belts, plates, lubricant
    "fail_pct": 7,           # share of prints that fail and go to the bin
    "labor_per_h": 400,      # ₽ per hour of your own work
    "setup_min": 10,         # slicing, starting the print, taking the plate off (per plate)
    "packaging": 30,         # ₽ per piece: box, bag, label
    "markup_pct": 120,       # your margin on top of cost
    "tax_pct": 6,            # УСН 6% / НПД 4–6%
    "commission_pct": 0,     # card acquiring, marketplace commission
    "nice_price": True,
    "printers": 1,           # for load planning
    "hours_per_day": 20,     # how long printers can work per day
}

NUM_KEYS = [k for k, v in DEFAULTS.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def merge_settings(saved: dict | None) -> dict:
    out = {**DEFAULTS, "materials": dict(DEFAULTS["materials"])}
    for k, v in (saved or {}).items():
        if k == "materials" and isinstance(v, dict) and v:
            out["materials"] = {str(n)[:40]: _num(p, 0) for n, p in list(v.items())[:40]}
        elif k in NUM_KEYS:
            out[k] = _num(v, DEFAULTS[k])
        elif k == "nice_price":
            out[k] = bool(v)
    return out


def _num(v: Any, default: float) -> float:
    try:
        x = float(str(v).replace(",", ".").replace(" ", ""))
        return x if math.isfinite(x) and x >= 0 else default
    except (TypeError, ValueError):
        return default


def nice(p: float) -> float:
    if p <= 0:
        return 0
    if p < 100:
        return math.ceil((p + 1) / 10) * 10 - 1          # 87 → 89
    if p < 5000:
        return math.ceil((p + 10) / 50) * 50 - 10        # 763 → 790, 795 → 840
    return math.ceil((p + 10) / 100) * 100 - 10          # 6420 → 6490


def calc(inp: dict, settings: dict) -> dict:
    """inp: material, grams, hours, minutes, pieces, finish_min, extras, markup_pct (optional override)."""
    s = merge_settings(settings)
    n = max(1, int(_num(inp.get("pieces"), 1) or 1))
    g = _num(inp.get("grams"), 0) / n
    t = (_num(inp.get("hours"), 0) + _num(inp.get("minutes"), 0) / 60) / n
    own = _num(inp.get("kg_price"), 0)  # the price of this very spool, when the maker typed it
    kg_price = own if own > 0 else s["materials"].get(inp.get("material") or "", None)
    if kg_price is None:
        kg_price = _num(inp.get("kg_price"), next(iter(s["materials"].values()), 1600))
    m = g * (1 + s["waste_pct"] / 100) * kg_price / 1000
    e = s["power_w"] / 1000 * t * s["kwh_price"]
    a = t * (s["printer_price"] / max(1, s["printer_life_h"]) + s["upkeep_per_h"])
    fail = min(s["fail_pct"], 90) / 100
    printing = (m + e + a) / (1 - fail)
    labour = (s["setup_min"] / n + _num(inp.get("finish_min"), 0)) / 60 * s["labor_per_h"]
    extras = _num(inp.get("extras"), 0)
    cost = printing + labour + s["packaging"] + extras
    markup = _num(inp.get("markup_pct"), s["markup_pct"]) if inp.get("markup_pct") not in (None, "") else s["markup_pct"]
    fees = min(s["tax_pct"] + s["commission_pct"], 90) / 100
    raw = cost * (1 + markup / 100) / (1 - fees)
    price = nice(raw) if s["nice_price"] else math.ceil(raw)
    profit = price * (1 - fees) - cost
    r = lambda x: round(x, 2)
    return {
        "grams": round(g, 1), "print_minutes": round(t * 60), "kg_price": kg_price,
        "plastic": r(m), "power": r(e), "wear": r(a), "failed": r(printing - m - e - a), "labour": r(labour),
        "packaging": r(s["packaging"]), "extras": r(extras),
        "cost": r(cost), "raw_price": r(raw), "price": r(price), "fees": r(price * fees),
        "profit": r(profit), "profit_per_hour": r(profit / t) if t > 0 else None, "markup_pct": markup,
    }
