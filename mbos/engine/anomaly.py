"""Daily anomaly detection: yesterday vs. the previous 7 days (z-score + % change).

We only flag a move when it is both statistically unusual (|z|) AND material (%),
so small accounts with noisy days don't flood the alert channel.
"""
from __future__ import annotations

import datetime as dt

from ..util import d, mean, pct, stdev
from . import metrics as M

# metric -> which direction is bad ("up", "down", "both")
WATCH = {
    "spend": "both",
    "cpr": "up",
    "cpm": "up",
    "ctr": "down",
    "cvr": "down",
    "results": "down",
}
AR = {"spend": "الصرف", "cpr": "تكلفة النتيجة", "cpm": "CPM", "ctr": "CTR",
      "cvr": "معدل التحويل", "results": "النتائج"}


def _series(rows, end, objective, filt=None):
    days = M.daily(rows, objective, filt)
    dates = [str(end - dt.timedelta(days=i)) for i in range(7, -1, -1)]
    return [days.get(x) for x in dates]  # 8 points: 7 baseline + yesterday


def detect(bundle, cfg):
    acc = bundle["account"]
    obj = acc["business"]["objective"]
    end = d(bundle["as_of"])
    th = cfg["thresholds"]["anomaly"]
    rows = bundle["rows"]
    out = []

    entities = [("account", acc["name"], None)]
    for c in bundle["campaigns"]:
        if c.get("status") == "ACTIVE":
            cid = c["id"]
            entities.append(("campaign", c["name"], lambda r, cid=cid: r["campaign_id"] == cid))

    account_tracking_break = False
    for level, name, filt in entities:
        s = _series(rows, end, obj, filt)
        base, y = s[:-1], s[-1]
        base = [b for b in base if b]
        if len(base) < 4:
            continue
        base_spend = mean([b["spend"] for b in base])
        if base_spend < th["min_daily_spend"]:
            continue
        y = y or M.derive(M.empty(), obj)

        # Hard rule: delivery stopped.
        if y["spend"] == 0:
            out.append(_a(level, name, "spend", 0, base_spend, -1.0, None, "critical",
                          "التوصيل وقف تماماً امبارح — راجع الرصيد/حالة الأكونت/رفض الإعلانات"))
            continue

        # Hard rule: clicks normal but conversions vanished -> tracking before optimisation.
        base_clicks = mean([b["clicks"] for b in base])
        base_res = mean([b["results"] for b in base])
        if base_res >= th["tracking_min_daily_results"] and y["results"] == 0 and y["clicks"] >= 0.5 * base_clicks:
            if level == "campaign" and account_tracking_break:
                continue  # already reported once at account level
            account_tracking_break = account_tracking_break or level == "account"
            out.append(_a(level, name, "results", 0, base_res, -1.0, None, "critical",
                          "الكليكات طبيعية والنتائج صفر — غالباً مشكلة تراكينج (Pixel/CAPI) أو صفحة الهبوط، مش مشكلة إعلانات"))
            continue

        for m, bad in WATCH.items():
            # Rate metrics on a handful of conversions a day are mostly Poisson noise.
            if m in ("cpr", "cvr", "results") and base_res < th["min_daily_results_for_rates"]:
                continue
            vals = [b.get(m) for b in base if b.get(m) is not None]
            yv = y.get(m)
            if yv is None or len(vals) < 4:
                continue
            mu, sd = mean(vals), stdev(vals)
            ch = pct(yv, mu)
            if ch is None:
                continue
            z = (yv - mu) / sd if sd else (0 if yv == mu else 9.9 * (1 if yv > mu else -1))
            direction_bad = (bad == "both") or (bad == "up" and ch > 0) or (bad == "down" and ch < 0)
            if not direction_bad:
                continue
            if abs(z) >= th["z_critical"] and abs(ch) >= th["pct_critical"]:
                sev = "critical"
            elif abs(z) >= th["z_warning"] and abs(ch) >= th["pct_warning"]:
                sev = "warning"
            else:
                continue
            out.append(_a(level, name, m, yv, mu, ch, z, sev, _hint(m, ch)))
    return out


def _a(level, name, metric, value, baseline, change, z, severity, hint):
    return {"level": level, "entity": name, "metric": metric, "metric_ar": AR.get(metric, metric),
            "value": value, "baseline": baseline, "change": change, "z": z,
            "severity": severity, "hint": hint}


def _hint(m, ch):
    up = ch > 0
    return {
        "cpm": "CPM طالع: منافسة في المزاد/مواسم أو جمهور ضيق أو كريتيف relevance ضعيف. قارن CTR قبل ما تغيّر حاجة.",
        "ctr": "CTR نازل: علامة إرهاق كريتيف أو تغيّر في الجمهور. راجع الـ Frequency والـ Hook rate للإعلانات الأعلى صرف.",
        "cvr": "التحويل نازل والترافيك موجود: راجع صفحة الهبوط/السعر/المخزون/سرعة الموقع قبل الإعلانات.",
        "cpr": "تكلفة النتيجة طالعة: حدد السبب من السلسلة (CPM ← CTR ← CVR) قبل أي تعديل ميزانية.",
        "results": "النتائج نازلة: تأكد إنها مش مشكلة تراكينج أو تأخير في الـ attribution قبل التصرف.",
        "spend": "الصرف زاد بشكل غير طبيعي — راجع أي تعديل ميزانية أو Advantage+ بيصرف أسرع." if up
                 else "الصرف قل: مشكلة توصيل (رصيد، رفض، Learning، Bid cap ضيق).",
    }[m]
