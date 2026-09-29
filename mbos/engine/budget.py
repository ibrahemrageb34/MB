"""Budget allocation inside one account.

Accounts are separate brands/clients, so money is never moved *between* accounts;
it is re-allocated between the budget holders (CBO campaign or ABO ad set) of one
account, capped by what the prepaid wallet can actually fund.
"""
from __future__ import annotations

import calendar

from ..util import d, div
from . import metrics as M


def budget_holders(bundle):
    """Where budget lives: CBO campaign (campaign.daily_budget) or ABO ad sets."""
    out = []
    for c in bundle["campaigns"]:
        if c.get("status") != "ACTIVE":
            continue
        if c.get("daily_budget"):
            out.append({"type": "campaign", "id": c["id"], "name": c["name"], "budget": c["daily_budget"],
                        "filter": ("campaign_id", c["id"]), "role": c.get("role", "")})
        else:
            for a in bundle["adsets"]:
                if a["campaign_id"] == c["id"] and a.get("status") == "ACTIVE" and a.get("daily_budget"):
                    out.append({"type": "adset", "id": a["id"], "name": a["name"], "budget": a["daily_budget"],
                                "filter": ("adset_id", a["id"]), "role": c.get("role", "")})
    return out


def recommend(bundle, cfg, prepaid, freeze_reason=None):
    acc = bundle["account"]
    biz = acc["business"]
    obj, target = biz["objective"], biz["target_cpa"]
    r = cfg["budget_rules"]
    end = d(bundle["as_of"])
    rows7 = M.window(bundle["rows"], end, 7)
    rows3 = M.window(bundle["rows"], end, 3)
    wallet_ok = prepaid.get("status") in ("ok", "unknown")
    recs = []
    for h in budget_holders(bundle):
        k, v = h["filter"]
        m7 = M.total([x for x in rows7 if x[k] == v], obj)
        m3 = M.total([x for x in rows3 if x[k] == v], obj)
        ratio = div(m7["cpr"], target) if m7["cpr"] is not None else None
        enough = m7["spend"] >= r["min_spend_x_cpa"] * target
        action, change, why = "hold", 0.0, ""
        if h["role"] == "testing":
            action, why = "hold", "كامبين اختبار — الميزانية ثابتة، القرار على مستوى الإعلان (Testing board)"
        elif not enough:
            action, why = "hold", "لسه مفيش داتا كفاية للحكم"
        elif m7["results"] == 0 or (ratio and ratio >= r["pause_ratio"]):
            action, change = "cut", -r["cut_step"] * 2
            why = f"تكلفة النتيجة {_x(ratio)} التارجت بعد صرف كافي"
        elif ratio <= r["scale_ratio"] and m7["results"] >= r["min_results_to_scale"]:
            recent_ok = m3["cpr"] is not None and m3["cpr"] <= target
            if recent_ok:
                action, change = "scale", r["scale_step"]
                why = f"CPR 7 أيام {_x(ratio)} التارجت و3 أيام الأخيرة تحت التارجت"
            else:
                action, why = "hold", "كويس على 7 أيام بس آخر 3 أيام أضعف — استنى"
        elif ratio >= r["cut_ratio"]:
            action, change = "cut", -r["cut_step"]
            why = f"CPR {_x(ratio)} التارجت"
        else:
            why = "في نطاق التارجت"
        if action == "scale" and not wallet_ok:
            action, change = "hold", 0.0
            why += " — لكن الرصيد مش كفاية: اشحن الأول وبعدين زوّد"
        elif action == "scale" and freeze_reason:
            action, change = "hold", 0.0
            why += f" — لكن {freeze_reason}: متزوّدش لحد ما السبب يتحدد"
        new_budget = round(h["budget"] * (1 + change))
        recs.append({"holder": h["type"], "id": h["id"], "name": h["name"], "current": h["budget"],
                     "recommended": new_budget, "change": change, "action": action, "why": why,
                     "spend7": m7["spend"], "results7": m7["results"], "cpr7": m7["cpr"],
                     "cpr3": m3["cpr"], "roas7": m7["roas"]})
    return recs


def pacing(bundle):
    """Month pacing vs. the monthly budget in config."""
    acc = bundle["account"]
    biz = acc["business"]
    end = d(bundle["as_of"])
    first = end.replace(day=1)
    days_in_month = calendar.monthrange(end.year, end.month)[1]
    mtd_rows = [r for r in bundle["rows"] if first <= d(r["date"]) <= end]
    mtd = M.total(mtd_rows, biz["objective"])
    elapsed = (end - first).days + 1
    remaining = days_in_month - elapsed
    monthly = biz.get("monthly_budget")
    out = {"mtd_spend": mtd["spend"], "mtd_results": mtd["results"], "days_elapsed": elapsed,
           "days_remaining": remaining, "monthly_budget": monthly}
    if monthly:
        out["expected_mtd"] = monthly * elapsed / days_in_month
        out["pace"] = div(mtd["spend"], out["expected_mtd"])
        out["daily_to_hit_budget"] = div(monthly - mtd["spend"], remaining) if remaining else 0
    return out


def _x(ratio):
    return f"{ratio:.2f}×" if ratio is not None else "—"
