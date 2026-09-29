"""Small shared helpers (stdlib only)."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def today() -> dt.date:
    override = os.environ.get("MBOS_TODAY")
    return dt.date.fromisoformat(override) if override else dt.date.today()


def d(s) -> dt.date:
    return s if isinstance(s, dt.date) else dt.date.fromisoformat(str(s)[:10])


def daterange(end: dt.date, days: int) -> list[dt.date]:
    """`days` dates ending at `end` (inclusive), oldest first."""
    return [end - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]


def div(a, b, default=None):
    try:
        return a / b if b else default
    except TypeError:
        return default


def mean(xs, default=0.0):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else default


def median(xs, default=0.0):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else default


def stdev(xs):
    xs = [x for x in xs if x is not None]
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def pct(a, b):
    """Relative change of a vs b (0.25 = +25%)."""
    if b in (0, None) or a is None:
        return None
    return (a - b) / abs(b)


def money(x, cur="EGP"):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:,.0f} {cur}"


def num(x, digits=0):
    if x is None:
        return "—"
    return f"{x:,.{digits}f}"


def pctfmt(x, digits=1):
    if x is None:
        return "—"
    return f"{x * 100:+.{digits}f}%"


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in s).strip("_")


def parse_tags(ad_name: str) -> dict:
    """Parse the creative naming convention.

    Convention (see docs/NAMING.md):  F:UGC | A:Pain | H:Question | O:FreeShip | T:T012 | v2
    Unknown tokens are ignored, so partially-tagged names still work.
    """
    tags = {}
    keys = {"F": "format", "A": "angle", "H": "hook", "O": "offer", "T": "test", "P": "persona"}
    for tok in (ad_name or "").split("|"):
        tok = tok.strip()
        if ":" in tok:
            k, v = tok.split(":", 1)
            k = k.strip().upper()
            if k in keys and v.strip():
                tags[keys[k]] = v.strip()
    return tags
