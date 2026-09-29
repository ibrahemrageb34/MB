"""Month-end forecast from the 7-day run-rate + a 14-day CPR trend."""
from __future__ import annotations

import calendar

from ..util import d, div
from . import metrics as M


def _slope(ys):
    n = len(ys)
    if n < 3:
        return 0.0
    xs = range(n)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def forecast(bundle):
    biz = bundle["account"]["business"]
    obj = biz["objective"]
    end = d(bundle["as_of"])
    days_in_month = calendar.monthrange(end.year, end.month)[1]
    remaining = days_in_month - end.day
    first = end.replace(day=1)
    mtd = M.total([r for r in bundle["rows"] if first <= d(r["date"]) <= end], obj)
    last7 = M.total(M.window(bundle["rows"], end, 7), obj)
    rr_spend, rr_res, rr_rev = last7["spend"] / 7, last7["results"] / 7, last7["revenue"] / 7

    series = M.daily(M.window(bundle["rows"], end, 14), obj)
    cprs = [v["cpr"] for v in series.values() if v["cpr"] is not None]
    slope = _slope(cprs)
    avg = sum(cprs) / len(cprs) if cprs else None
    weekly_trend = div(slope * 7, avg)

    proj_spend = mtd["spend"] + rr_spend * remaining
    proj_res = mtd["results"] + rr_res * remaining
    proj_rev = mtd["revenue"] + rr_rev * remaining
    return {
        "month_end_spend": proj_spend,
        "month_end_results": proj_res,
        "month_end_revenue": proj_rev,
        "month_end_cpr": div(proj_spend, proj_res),
        "month_end_roas": div(proj_rev, proj_spend),
        "next7_spend": rr_spend * 7,
        "cpr_weekly_trend": weekly_trend,
        "vs_budget": div(proj_spend, biz.get("monthly_budget")),
        "note": "توقع خطي على معدل آخر 7 أيام — مش بياخد في اعتباره المواسم أو تغييرات الميزانية.",
    }
