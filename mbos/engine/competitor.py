"""Competitor research from Meta Ad Library data.

Limitation: outside the EU/UK the Ad Library *API* only returns political/issue ads,
so for Egypt/MENA the input is usually a manual or scraped export saved to
data/competitors/<account_key>.json. Longevity (days an ad has been running) is the
most reliable public proxy for a profitable ad; it is a proxy, not proof.
"""
from __future__ import annotations

import re
from collections import Counter

from ..util import d
from .creative import classify_angle

DISCOUNT = re.compile(r"(\d{1,2})\s*%")


def analyze(ads, as_of, long_days=30):
    if not ads:
        return None
    as_of = d(as_of)
    pages = {}
    long_runners = []
    offers = Counter()
    angles = Counter()
    for a in ads:
        days = (as_of - d(a["start_date"])).days
        angle = a.get("angle") or classify_angle(a.get("text", ""))
        pg = pages.setdefault(a["page"], {"page": a["page"], "active": 0, "new_7d": 0, "formats": Counter()})
        if a.get("is_active", True):
            pg["active"] += 1
            angles[angle] += 1
            if days >= long_days:
                long_runners.append({"page": a["page"], "days": days, "angle": angle, "format": a.get("format"),
                                     "text": (a.get("text") or "")[:140], "url": a.get("url")})
        if days <= 7:
            pg["new_7d"] += 1
        pg["formats"][a.get("format") or "?"] += 1
        m = DISCOUNT.search(a.get("text", ""))
        if m:
            offers[f"خصم {m.group(1)}%"] += 1
        if "مجاني" in a.get("text", "") or "free" in a.get("text", "").lower():
            offers["توصيل/هدية مجانية"] += 1
    long_runners.sort(key=lambda x: -x["days"])
    page_rows = [{**p, "formats": dict(p["formats"])} for p in pages.values()]
    page_rows.sort(key=lambda x: -x["active"])
    notes = []
    if long_runners:
        w = long_runners[0]
        notes.append(f"أطول إعلان شغال: {w['page']} ({w['days']} يوم) بزاوية «{w['angle']}» — ادرس الهوك والعرض.")
    surge = [p for p in page_rows if p["new_7d"] >= 5]
    for p in surge:
        notes.append(f"{p['page']} نزّل {p['new_7d']} إعلان جديد في آخر أسبوع — غالباً حملة/عرض جديد، راقب الـ CPM عندنا.")
    if offers:
        o, n = offers.most_common(1)[0]
        notes.append(f"العرض الأكثر تكراراً في السوق: {o} ({n} إعلان). قارن عرضنا بيه.")
    return {"pages": page_rows, "long_runners": long_runners[:8], "angles": dict(angles.most_common()),
            "offers": dict(offers.most_common()), "notes": notes}
