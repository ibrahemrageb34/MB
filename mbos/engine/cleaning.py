"""Data cleaning applied to every bundle before analysis."""
from __future__ import annotations

from .metrics import BASE


def clean(bundle, cfg):
    report = {"duplicates": 0, "negative_values": 0, "excluded_test_campaigns": 0, "orphans": 0}
    exclude = [x.lower() for x in cfg["cleaning"]["exclude_campaign_keywords"]]
    excluded = {c["id"] for c in bundle["campaigns"] if any(k in c["name"].lower() for k in exclude)}
    report["excluded_test_campaigns"] = len(excluded)
    known_ads = {a["id"] for a in bundle["ads"]}

    seen, rows = set(), []
    for r in bundle["rows"]:
        key = (str(r["date"])[:10], r["ad_id"])
        if key in seen:
            report["duplicates"] += 1
            continue
        seen.add(key)
        if r["campaign_id"] in excluded:
            continue
        if r["ad_id"] not in known_ads:
            report["orphans"] += 1
        for k in BASE:
            v = r.get(k) or 0
            if v < 0:
                report["negative_values"] += 1
                v = 0
            r[k] = float(v)
        r["date"] = str(r["date"])[:10]
        rows.append(r)
    bundle["rows"] = rows
    bundle["campaigns"] = [c for c in bundle["campaigns"] if c["id"] not in excluded]
    bundle["cleaning"] = report
    return bundle
