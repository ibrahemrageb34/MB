"""Split one ad account into lanes: one lane per result type (website sales, messages,
leads, app registrations...). A CPR only means something when every campaign in it chases
the same result, so each lane is analysed on its own with its own target.

accounts.json -> "lanes": [
  {"name": "رسايل", "objective": "message", "target_cpa": 40},
  {"name": "سواقين", "objective": "registration", "keywords": ["DRIVER", "سواق"]}
]
A campaign joins the first lane whose keyword appears in its name, else the first lane
whose objective matches the campaign's optimisation. Campaigns that match no lane get an
automatic lane. A lane without target_cpa is judged against its own 30-day average.
"""
from __future__ import annotations

import copy

from .engine import metrics as M
from .util import d, div, slug

# Fallback targets (EGP) only when a lane has no target and no history yet. Rough starting
# points, flagged as assumptions on the dashboard; replace with real numbers asap.
DEFAULT_TARGETS = {"purchase": 500, "lead": 250, "message": 30, "install": 25, "registration": 60,
                   "traffic": 4, "awareness": 0.05}


def split(bundle):
    acc = bundle["account"]
    biz = acc["business"]
    lanes = [dict(x) for x in acc.get("lanes") or
             [{"name": "", "objective": biz["objective"], "target_cpa": biz.get("target_cpa")}]]
    assign = {}
    for c in bundle["campaigns"]:
        name = c["name"].lower()
        result = c.get("result") or biz["objective"]
        hit = next((i for i, ln in enumerate(lanes)
                    if any(k.lower() in name for k in ln.get("keywords", []))), None)
        if hit is None:
            hit = next((i for i, ln in enumerate(lanes)
                        if ln["objective"] == result and not ln.get("keywords")), None)
        if hit is None:
            obj = result
            hit = next((i for i, ln in enumerate(lanes) if ln.get("auto") and ln["objective"] == obj), None)
            if hit is None:
                lanes.append({"name": f"{M.RESULT_LABEL.get(obj, obj)} (تلقائي)", "objective": obj, "auto": True})
                hit = len(lanes) - 1
        assign[c["id"]] = hit

    out = []
    end = d(bundle["as_of"])
    for i, ln in enumerate(lanes):
        camp_ids = {cid for cid, h in assign.items() if h == i}
        rows = [r for r in bundle["rows"] if r["campaign_id"] in camp_ids]
        if not camp_ids or (i > 0 and not rows):
            continue
        b = copy.copy(bundle)
        b["campaigns"] = [c for c in bundle["campaigns"] if c["id"] in camp_ids]
        b["adsets"] = [a for a in bundle["adsets"] if a["campaign_id"] in camp_ids]
        b["ads"] = [a for a in bundle["ads"] if a["campaign_id"] in camp_ids]
        b["rows"] = rows
        assumptions = list(acc.get("assumptions", []))
        target = ln.get("target_cpa")
        if not target:
            m30 = M.total(M.window(rows, end, 30), ln["objective"])
            if m30["cpr"]:
                target = round(m30["cpr"], 2)
                assumptions.append(f"مفيش تارجت لـ «{ln['name'] or ln['objective']}» — بنقارن بمتوسط آخر 30 يوم ({target:,.0f}). حدّد رقم حقيقي.")
            else:
                target = DEFAULT_TARGETS.get(ln["objective"], 100)
                assumptions.append(f"مفيش تارجت ولا تاريخ لـ «{ln['name'] or ln['objective']}» — رقم مبدئي {target:,.0f} لحد ما يبقى فيه داتا.")
        a2 = copy.deepcopy(acc)
        a2["business"] = {**biz, "objective": ln["objective"], "target_cpa": target}
        a2["assumptions"] = assumptions
        a2["brand"] = acc.get("brand") or acc["name"]
        a2["lane"] = ln.get("name") or ""
        base_code = acc.get("code") or slug(acc["name"])
        a2["code"] = base_code if i == 0 else f"{base_code}-{slug(ln.get('name') or ln['objective'])}"
        a2["name"] = f"{acc['name']} · {ln['name']}" if ln.get("name") else acc["name"]
        b["account"] = a2
        b["primary_lane"] = not out
        if not b["primary_lane"]:
            b["posts"], b["competitors"] = [], []  # page-level data lives on the primary lane only
        out.append(b)
    return out


def lane_share(lane_bundle, full_bundle, days=7):
    """Share of the ad account's recent spend that this lane represents."""
    end = d(full_bundle["as_of"])
    tot = M.total(M.window(full_bundle["rows"], end, days))["spend"]
    part = M.total(M.window(lane_bundle["rows"], end, days))["spend"]
    return div(part, tot, 0)
