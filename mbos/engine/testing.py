"""Creative Testing System: every test has a hypothesis, one variable, and pre-agreed
success/failure criteria. The engine only *scores* tests against those criteria; it
never invents the criteria after seeing the data.

Tests live in data/tests/<account_key>.json. Ads are linked to a test by the `T:<id>`
token in the ad name (docs/NAMING.md).
"""
from __future__ import annotations

from ..util import d, div, parse_tags
from . import metrics as M


def evaluate(bundle, tests, cfg):
    biz = bundle["account"]["business"]
    obj, target = biz["objective"], biz["target_cpa"]
    rules = cfg["testing"]
    ads = {a["id"]: a for a in bundle["ads"]}
    out = []
    for t in tests:
        start = d(t["start"])
        rows = [r for r in bundle["rows"] if d(r["date"]) >= start
                and parse_tags(ads.get(r["ad_id"], {}).get("name", "")).get("test") == t["id"]]
        variants = M.group(rows, "ad_id", obj)
        vres = []
        for ad_id, m in variants.items():
            v = _verdict(m, target, rules)
            vres.append({"ad_id": ad_id, "name": ads.get(ad_id, {}).get("name", ad_id), "spend": m["spend"],
                         "results": m["results"], "cpr": m["cpr"], "ctr": m["ctr"], "hook_rate": m["hook_rate"],
                         "verdict": v})
        vres.sort(key=lambda x: (x["cpr"] is None, x["cpr"] or 0))
        tot = M.total(rows, obj)
        if t.get("status") == "closed":
            status = t.get("result", "closed")
        elif not vres:
            status = "not_started"
        elif any(v["verdict"] == "winner" for v in vres):
            status = "winner"
        elif all(v["verdict"] == "loser" for v in vres):
            status = "loser"
        else:
            status = "running"
        days = (d(bundle["as_of"]) - start).days + 1
        nxt = {
            "winner": "خرّج الإعلان الكسبان للسكيل بنفس الـ Post ID، واعمل iteration على نفس الزاوية بهوك مختلف.",
            "loser": "اقفل الاختبار ووثّق الدرس: الفرضية اترفضت. جرّب زاوية تانية بدل ما تغيّر الفورمات بس.",
            "running": "كمّل لحد ما يوصل لحد الصرف المتفق عليه — متحكمش بدري.",
            "not_started": "مفيش إعلانات مربوطة بالاختبار — تأكد من T:<id> في اسم الإعلان.",
        }.get(status, "")
        if status == "running" and days > rules["max_days"]:
            status = "inconclusive"
            nxt = f"عدّى {rules['max_days']} أيام من غير نتيجة واضحة — اقفل وسجّله inconclusive (غالباً الفرق بين المتغيرات صغير)."
        out.append({**t, "status": status, "days": days, "spend": tot["spend"], "results": tot["results"],
                    "cpr": tot["cpr"], "variants": vres, "next": nxt})
    return out


def _verdict(m, target, r):
    spend, res, cpr = m["spend"], m["results"], m["cpr"]
    if res >= r["min_results_win"] and cpr is not None and cpr <= r["win_ratio"] * target:
        return "winner"
    if spend >= r["kill_spend_x_cpa"] * target and res == 0:
        return "loser"
    if spend >= r["decision_spend_x_cpa"] * target and cpr is not None and cpr >= r["lose_ratio"] * target:
        return "loser"
    return "learning"


def summary(evaluated):
    c = {}
    for t in evaluated:
        c[t["status"]] = c.get(t["status"], 0) + 1
    return {"counts": c, "win_rate": div(c.get("winner", 0), sum(v for k, v in c.items() if k in ("winner", "loser", "inconclusive")))}
