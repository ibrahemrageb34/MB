"""Runs every module for every account and assembles one result object that feeds
the dashboard, the CEO/Team reports, the 10-minute breakdown and the alerts."""
from __future__ import annotations

from . import ai, lanes
from .engine import (anomaly, budget, cleaning, competitor, creative, forecast, metrics as M,
                     prepaid, qa, roadmap, sales, testing)
from .util import ROOT, clamp, d, div, load_json, parse_tags, save_json, slug

PRIO = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def analyze_bundle(bundle, cfg, persist=False):
    """One ad account -> one result per lane. The prepaid wallet belongs to the ad
    account, so it is computed once on the whole account and shared by its lanes."""
    bundle = cleaning.clean(bundle, cfg)
    if ai.enabled(cfg):
        _ai_tags(bundle, cfg, persist)
    wallet = prepaid.analyze(bundle, cfg)
    out = []
    for lane in lanes.split(bundle):
        r = analyze_account(lane, cfg, persist_journal=persist and lane["primary_lane"], wallet=wallet)
        r["lane_share"] = lanes.lane_share(lane, bundle)
        out.append(r)
    return out


def _ai_tags(bundle, cfg, persist):
    """Fill angle/format/hook for ads whose names carry no tags (cached per ad id)."""
    code = bundle["account"].get("code") or slug(bundle["account"]["name"])
    path = ROOT / "data/tags" / f"{code}.json"
    cache = load_json(path, {})
    todo = [a for a in bundle["ads"] if a["id"] not in cache and a.get("text")
            and not parse_tags(a.get("name", "")).get("angle")]
    if todo:
        cache.update(ai.tag_ads(cfg, bundle["account"], todo[:cfg["ai"].get("max_tag_per_run", 40)]))
        if persist:
            save_json(path, cache)
    for a in bundle["ads"]:
        if a["id"] in cache:
            a["ai_tags"] = cache[a["id"]]


def analyze_account(bundle, cfg, persist_journal=False, wallet=None):
    acc = bundle["account"]
    biz = acc["business"]
    obj, target = biz["objective"], biz["target_cpa"]
    key = acc.get("code") or slug(acc["name"])
    bundle = cleaning.clean(bundle, cfg)
    end = d(bundle["as_of"])

    tests_def = bundle.get("tests") if "tests" in bundle else load_json(ROOT / "data/tests" / f"{key}.json", [])
    comp_ads = bundle.get("competitors") if "competitors" in bundle else load_json(ROOT / "data/competitors" / f"{key}.json", [])
    jpath = ROOT / "data/journal" / f"{key}.json"
    journal = bundle.get("journal") or roadmap.load(jpath)

    k7 = M.total(M.window(bundle["rows"], end, 7), obj)
    kprev = M.total(M.window(bundle["rows"], end.fromordinal(end.toordinal() - 7), 7), obj)
    ky = M.total(M.window(bundle["rows"], end, 1), obj)
    trend = M.daily(M.window(bundle["rows"], end, max(30, end.day)), obj)

    anomalies = anomaly.detect(bundle, cfg)
    issues = qa.check(bundle, cfg)
    wallet = wallet or prepaid.analyze(bundle, cfg)
    primary = bundle.get("primary_lane", True)
    crit = next((a for a in anomalies if a["severity"] == "critical" and a["level"] == "account"), None)
    budgets = budget.recommend(bundle, cfg, wallet, f"فيه anomaly حرجة امبارح ({crit['metric_ar']})" if crit else None)
    pace = budget.pacing(bundle)
    fc = forecast.forecast(bundle)
    table = creative.ad_table(bundle)
    ins = creative.insights(bundle, cfg, table)
    fat = creative.fatigue(table, cfg)
    if ai.enabled(cfg):
        for p in bundle.get("posts", []):
            p["ai"] = ai.analyze_post(cfg, acc, p) if _is_new(p, end, cfg) else None
    posts = creative.triage_posts(bundle, cfg, table, budgets)
    tests = testing.evaluate(bundle, tests_def or [], cfg)
    comp = competitor.analyze(comp_ads, end) if comp_ads else None
    ideas = creative.test_ideas(bundle, cfg, table, ins, fat, comp)

    journal = roadmap.merge(journal, roadmap.auto_events(str(end), anomalies, wallet, tests, issues))
    if persist_journal:
        roadmap.save(jpath, journal)

    actions = build_actions(acc, cfg, k7, anomalies, issues, wallet if primary else {}, budgets, fat, posts, tests)
    health = health_score(k7, target, obj, biz, wallet, anomalies, issues, fat)

    return {
        "key": key, "name": acc["name"], "owner": acc.get("owner"), "team": acc.get("team", {}),
        "brand": acc.get("brand") or acc["name"], "lane": acc.get("lane", ""), "primary": primary,
        "account_id": acc.get("id"), "assumptions": acc.get("assumptions", []),
        "sales_log": acc.get("sales_log"), "brand_targets": acc.get("brand_targets"),
        "platform": acc.get("platform", "meta"), "currency": bundle["info"].get("currency", "EGP"),
        "business": biz, "as_of": str(end), "health": health,
        "kpi": {"yesterday": ky, "last7": k7, "prev7": kprev}, "trend": trend,
        "anomalies": anomalies, "qa": issues, "prepaid": wallet, "budget": budgets, "pacing": pace,
        "forecast": fc, "creatives": table[:25], "creative_insights": ins, "fatigue": fat,
        "posts": posts, "tests": tests, "test_summary": testing.summary(tests), "ideas": ideas,
        "competitors": comp, "roadmap": roadmap.progress(journal),
        "roadmap_mermaid": roadmap.mermaid(acc["name"], journal), "actions": actions,
        "cleaning": bundle.get("cleaning"),
    }


def _is_new(p, end, cfg):
    import datetime as dt
    return (dt.datetime.combine(end, dt.time(23, 59)) - dt.datetime.fromisoformat(p["created_time"][:19])).total_seconds() \
        <= cfg["post_triage"]["new_post_hours"] * 3600


def health_score(k7, target, obj, biz, wallet, anomalies, issues, fat):
    s = 100.0
    ratio = div(k7["cpr"], target)
    if ratio is None:
        s -= 30
    elif ratio > 1:
        s -= min(35, (ratio - 1) * 70)
    if obj == "purchase" and biz.get("gross_margin") and k7["roas"] is not None:
        if k7["roas"] < 1 / biz["gross_margin"]:
            s -= 10  # below break-even ROAS
    s -= {"debt": 35, "critical": 25, "warning": 10}.get(wallet.get("status"), 0)
    s -= min(20, sum(10 if a["severity"] == "critical" else 4 for a in anomalies))
    s -= min(15, sum({"P0": 8, "P1": 4, "P2": 1, "P3": 0}[i["priority"]] for i in issues))
    s -= min(9, 3 * len(fat))
    s = round(clamp(s, 0, 100))
    status = "good" if s >= 75 else ("warning" if s >= 50 else "critical")
    if wallet.get("status") in ("debt", "critical"):
        status = "critical"  # an account about to stop is never "fine", whatever its CPR
    elif status == "good" and any(i["priority"] == "P0" for i in issues):
        status = "warning"
    return {"score": s, "status": status, "cpr_ratio": ratio}


def build_actions(acc, cfg, k7, anomalies, issues, wallet, budgets, fat, posts, tests):
    """One prioritised action list per account (Impact × Confidence ÷ Effort)."""
    team = acc.get("team", {})
    roles = cfg["roles"]
    acts = []

    def add(p, area, title, why, how, role, due, kpi, impact, effort, conf):
        acts.append({"priority": p, "area": area, "title": title, "why": why, "how": how, "owner_role": role,
                     "owner": team.get(role) or roles[role]["title"], "tool": roles[role]["tool"], "due": due,
                     "kpi": kpi, "ice": round(impact * conf / effort, 1), "account": acc["name"]})

    if wallet.get("status") in ("debt", "critical"):
        add("P0", "prepaid", "شحن الرصيد + تثبيت حد الإنفاق", wallet["message"],
            f"شحن {wallet.get('topup_recommended', 0):,.0f} ثم Spending limit = {wallet.get('spend_cap_recommended', 0):,.0f}",
            "finance", "النهارده", "Runway ≥ 7 أيام", 10, 1, 10)
    elif wallet.get("status") == "warning":
        add("P1", "prepaid", "جدولة شحن الرصيد", wallet["message"], f"شحن {wallet.get('topup_recommended', 0):,.0f} قبل {wallet.get('topup_by')}",
            "finance", wallet.get("topup_by", "خلال 48 ساعة"), "Runway ≥ 7 أيام", 7, 1, 9)
    # One action per metric: account-level critical = P0, campaign-level only = P1.
    grouped = {}
    for a in anomalies:
        if a["severity"] == "critical":
            grouped.setdefault(a["metric"], []).append(a)
    for metric, group in grouped.items():
        acct_level = any(x["level"] == "account" for x in group)
        lead = next((x for x in group if x["level"] == "account"), group[0])
        names = "، ".join(x["entity"] for x in group if x["level"] == "campaign")
        owner = "tracking" if "تراكينج" in lead["hint"] else "media_buyer"
        add("P0" if acct_level else "P1", "anomaly", f"{lead['metric_ar']} {lead['change'] * 100:+.0f}%" + (" (الأكونت كله)" if acct_level else ""),
            f"امبارح مقابل متوسط 7 أيام" + (f" · الكامبينات: {names}" if names else f" · {lead['entity']}"), lead["hint"],
            owner, "النهارده", lead["metric_ar"], 8 if acct_level else 5, 2, 7)
    for i in issues[:6]:
        add(i["priority"], i["area"], i["title"], i["entity"], i["why"], i["owner"],
            "النهارده" if i["priority"] in ("P0", "P1") else "الأسبوع ده", "QA clean", 6 if i["priority"] in ("P0", "P1") else 3, 1, 8)
    for b in budgets:
        if b["action"] == "scale":
            add("P1", "budget", f"زوّد ميزانية {b['name']} {b['change'] * 100:+.0f}%", b["why"],
                f"{b['current']:,.0f} ← {b['recommended']:,.0f}/يوم، وراجع بعد 72 ساعة", "media_buyer", "النهارده", "CPR ≤ التارجت بعد السكيل", 8, 1, 7)
        elif b["action"] == "cut":
            add("P1", "budget", f"قلّل/وقّف {b['name']}", b["why"], f"{b['current']:,.0f} ← {b['recommended']:,.0f}/يوم",
                "media_buyer", "النهارده", "CPR الأكونت", 7, 1, 8)
    for f in fat[:3]:
        add("P1", "creative", f"استبدال كريتيف مرهق: {f['name']}", f["reason"], "نفس الزاوية بهوك وأول 3 ثواني جداد (راجع أفكار الاختبار)",
            "creative", "خلال 48 ساعة", "CTR يرجع لمستواه", 6, 3, 7)
    for p in posts:
        if p["verdict"] == "promote":
            add("P1", "creative", f"تحويل بوست لإعلان ({p['angle']}) — Score {p['score']}", "; ".join(p["why"][:2]), p["how"],
                "media_buyer", "النهارده", "CPR الإعلان ≤ التارجت", 6, 1, 6)
    for t in tests:
        if t["status"] in ("winner", "loser", "inconclusive"):
            add("P2", "testing", f"إغلاق اختبار {t['id']} ({t['status']})", t["hypothesis"], t["next"],
                "creative" if t["status"] != "winner" else "media_buyer", "خلال 48 ساعة", "Test velocity", 5, 1, 8)
    acts.sort(key=lambda x: (PRIO[x["priority"]], -x["ice"]))
    return acts


def portfolio(results, cfg):
    tot7 = {"spend": 0.0, "revenue": 0.0}
    for r in results:
        tot7["spend"] += r["kpi"]["last7"]["spend"]
        tot7["revenue"] += r["kpi"]["last7"]["revenue"]
    wallets = {r["name"]: r["prepaid"] for r in results if r.get("primary", True)}
    alerts = []
    for r in results:
        for a in r["actions"]:
            if a["priority"] == "P0":
                alerts.append({"account": r["name"], **a})
    return {"spend7": tot7["spend"], "revenue7": tot7["revenue"],
            "brands": brands(results),
            "treasury": prepaid.treasury(wallets),
            "health": sorted([{"name": r["name"], **r["health"]} for r in results], key=lambda x: x["score"]),
            "p0": alerts}


def brands(results):
    """Brand-level view: all lanes and ad accounts of a brand + its sales log."""
    out = {}
    for r in results:
        b = out.setdefault(r["brand"], {"brand": r["brand"], "lanes": [], "spend_by_day": {}, "spend7": 0.0,
                                         "sales_log": None, "targets": None, "as_of": r["as_of"]})
        b["lanes"].append({"name": r["name"], "health": r["health"]["score"], "status": r["health"]["status"]})
        b["spend7"] += r["kpi"]["last7"]["spend"]
        for day, m in r["trend"].items():
            b["spend_by_day"][day] = b["spend_by_day"].get(day, 0.0) + m["spend"]
        b["sales_log"] = b["sales_log"] or r.get("sales_log")
        b["targets"] = b["targets"] or r.get("brand_targets")
    rows = []
    for b in out.values():
        s = sales.summarize(sales.load(b["sales_log"]), b["spend_by_day"], b["as_of"], b["targets"])
        rows.append({"brand": b["brand"], "lanes": b["lanes"], "spend7": b["spend7"], "sales": s,
                     "targets": b["targets"] or {}})
    return rows
