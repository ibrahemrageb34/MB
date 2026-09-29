"""Search-term analysis (Google Ads / Microsoft Ads). Ready for phase 2.

Meta has no search terms, so this runs only when a search-terms CSV/rows are supplied:
  columns: search_term, clicks, cost, conversions, conv_value
"""
from __future__ import annotations

from collections import defaultdict

from ..util import div


def analyze(rows, target_cpa, min_cost_x_cpa=1.5):
    negatives, promote, ngrams = [], [], defaultdict(lambda: {"cost": 0.0, "conv": 0.0, "terms": 0})
    for r in rows:
        cost, conv = float(r.get("cost", 0)), float(r.get("conversions", 0))
        term = r["search_term"].strip().lower()
        if conv == 0 and cost >= min_cost_x_cpa * target_cpa:
            negatives.append({"term": term, "cost": cost, "clicks": r.get("clicks")})
        elif conv >= 2 and div(cost, conv, 1e9) <= target_cpa:
            promote.append({"term": term, "cost": cost, "conversions": conv, "cpa": div(cost, conv)})
        for w in set(term.split()):
            g = ngrams[w]
            g["cost"] += cost
            g["conv"] += conv
            g["terms"] += 1
    waste_words = [{"word": w, **v, "cpa": div(v["cost"], v["conv"])} for w, v in ngrams.items()
                   if v["terms"] >= 3 and v["conv"] == 0 and v["cost"] >= target_cpa]
    waste_words.sort(key=lambda x: -x["cost"])
    return {"negative_candidates": sorted(negatives, key=lambda x: -x["cost"]),
            "exact_match_candidates": sorted(promote, key=lambda x: x["cpa"]),
            "negative_words": waste_words[:20],
            "wasted_spend": sum(n["cost"] for n in negatives)}
