"""Aggregation + derived KPIs. Every other module reads metrics through here."""
from __future__ import annotations

from collections import defaultdict

from ..util import d, div

BASE = ["spend", "impressions", "reach", "clicks", "lpv", "atc", "ic", "purchases",
        "revenue", "leads", "messages", "video_3s", "thruplay", "installs", "registrations"]

RESULT_KEY = {"purchase": "purchases", "lead": "leads", "message": "messages", "install": "installs",
              "registration": "registrations", "traffic": "lpv", "awareness": "reach"}
RESULT_LABEL = {"purchase": "طلب", "lead": "ليد", "message": "محادثة", "install": "تثبيت",
                "registration": "تسجيل", "traffic": "زيارة", "awareness": "وصول"}


def result_key(objective: str) -> str:
    return RESULT_KEY.get(objective, "purchases")


def empty():
    return {k: 0.0 for k in BASE}


def add(acc, row):
    for k in BASE:
        acc[k] += float(row.get(k) or 0)
    return acc


def derive(m, objective="purchase"):
    """Return a copy of summed metrics `m` with derived KPIs attached."""
    out = dict(m)
    rk = result_key(objective)
    res = m.get(rk, 0)
    out["results"] = res
    out["cpr"] = div(m["spend"], res)
    out["ctr"] = div(m["clicks"], m["impressions"])
    out["cpc"] = div(m["spend"], m["clicks"])
    out["cpm"] = div(m["spend"] * 1000, m["impressions"])
    out["cvr"] = div(res, m["clicks"])
    out["roas"] = div(m["revenue"], m["spend"])
    out["aov"] = div(m["revenue"], m["purchases"])
    out["hook_rate"] = div(m["video_3s"], m["impressions"])
    out["hold_rate"] = div(m["thruplay"], m["video_3s"])
    out["lpv_rate"] = div(m["lpv"], m["clicks"])
    out["atc_rate"] = div(m["atc"], m["lpv"])
    out["checkout_rate"] = div(m["purchases"], m["ic"])
    return out


def window(rows, end, days):
    """Rows whose date is in the `days`-day window ending at `end` (inclusive)."""
    end = d(end)
    lo = end.toordinal() - days + 1
    return [r for r in rows if lo <= d(r["date"]).toordinal() <= end.toordinal()]


def total(rows, objective="purchase"):
    acc = empty()
    for r in rows:
        add(acc, r)
    return derive(acc, objective)


def group(rows, key, objective="purchase"):
    """Sum rows by `key` (a field name or a callable) -> {key: derived metrics}."""
    buckets = defaultdict(empty)
    for r in rows:
        k = key(r) if callable(key) else r.get(key)
        add(buckets[k], r)
    return {k: derive(v, objective) for k, v in buckets.items()}


def daily(rows, objective="purchase", filt=None):
    """{date_iso: derived metrics} for rows (optionally filtered)."""
    rows = [r for r in rows if filt is None or filt(r)]
    return dict(sorted(group(rows, lambda r: str(d(r["date"])), objective).items()))
