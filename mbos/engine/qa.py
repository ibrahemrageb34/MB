"""Campaign QA: structural and hygiene problems that silently waste budget."""
from __future__ import annotations

import re

from ..util import d
from . import metrics as M


def check(bundle, cfg):
    acc = bundle["account"]
    obj = acc["business"]["objective"]
    target = acc["business"]["target_cpa"]
    th = cfg["thresholds"]
    end = d(bundle["as_of"])
    rows7 = M.window(bundle["rows"], end, 7)
    by_ad = M.group(rows7, "ad_id", obj)
    by_adset = M.group(rows7, "adset_id", obj)
    issues = []
    camp_re = re.compile(cfg["naming"]["campaign_regex"])

    active_camps = [c for c in bundle["campaigns"] if c.get("status") == "ACTIVE"]
    camp_ids = {c["id"] for c in active_camps}
    for c in active_camps:
        if not camp_re.match(c["name"]):
            issues.append(_i("P3", "naming", c["name"], "اسم الكامبين خارج الـ naming convention",
                             "التسمية الموحدة هي اللي بتخلي التقارير والـ breakdown أوتوماتيك", "media_buyer"))
        ads = [a for a in bundle["ads"] if a["campaign_id"] == c["id"] and a.get("status") == "ACTIVE"]
        if not ads:
            issues.append(_i("P1", "delivery", c["name"], "كامبين شغالة من غير أي إعلان Active",
                             "الميزانية محجوزة ومفيش توصيل", "media_buyer"))

    for a in bundle["adsets"]:
        if a["campaign_id"] not in camp_ids or a.get("status") != "ACTIVE":
            continue
        m = by_adset.get(a["id"])
        if a.get("learning_stage") == "LEARNING_LIMITED":
            issues.append(_i("P1", "learning", a["name"], "Learning Limited",
                             "مش بيوصل لعدد تحويلات كافي أسبوعياً — ادمج ad sets أو كبّر الميزانية أو انقل الـ optimization event لخطوة أعلى في الفانل",
                             "media_buyer"))
        budget = a.get("daily_budget")
        if budget and target and budget < th["min_budget_x_cpa"] * target:
            issues.append(_i("P2", "budget", a["name"],
                             f"الميزانية اليومية {budget:,.0f} أقل من {th['min_budget_x_cpa']}× التارجت CPA",
                             "مش هيطلع من الـ Learning بالمعدل ده (~50 تحويل/أسبوع)", "media_buyer"))
        n_ads = sum(1 for x in bundle["ads"] if x["adset_id"] == a["id"] and x.get("status") == "ACTIVE")
        if n_ads > th["max_active_ads_per_adset"]:
            issues.append(_i("P2", "structure", a["name"], f"{n_ads} إعلانات Active في نفس الـ ad set",
                             "الصرف بيتوزع على إعلانات كتير ومفيش إعلان بياخد داتا كفاية", "media_buyer"))
        if m and a.get("audience_type") == "prospecting":
            f7 = max((bundle["freq7"].get(x["id"], 0) for x in bundle["ads"] if x["adset_id"] == a["id"]), default=0)
            if f7 > th["max_frequency_prospecting"]:
                issues.append(_i("P2", "fatigue", a["name"], f"Frequency 7 أيام = {f7:.1f}",
                                 "الجمهور بيتشبع — محتاج كريتيف جديد أو توسيع الجمهور", "creative"))

    for ad in bundle["ads"]:
        if ad["campaign_id"] not in camp_ids:
            continue
        if ad.get("review_status") in ("DISAPPROVED", "WITH_ISSUES"):
            issues.append(_i("P0", "policy", ad["name"], f"الإعلان {ad['review_status']}",
                             "مرفوض/فيه مشاكل — عدّل أو اعمل appeal. الرفض المتكرر بيأثر على جودة الأكونت", "media_buyer"))
        if ad.get("status") == "ACTIVE" and not ad.get("url_tags") and obj != "message":
            issues.append(_i("P2", "tracking", ad["name"], "مفيش UTM parameters",
                             "مش هتقدر تقارن داتا ميتا بـ GA4/المتجر", "tracking"))
        m = by_ad.get(ad["id"])
        if m and ad.get("status") == "ACTIVE" and target:
            if m["results"] == 0 and m["spend"] >= th["kill_spend_x_cpa"] * target:
                issues.append(_i("P1", "waste", ad["name"],
                                 f"صرف {m['spend']:,.0f} (≥{th['kill_spend_x_cpa']}× التارجت) بدون ولا نتيجة",
                                 "اقفله أو انقله لاختبار تاني بزاوية مختلفة", "media_buyer"))

    info = bundle["info"]
    if info.get("pixel_ok") is False:
        issues.append(_i("P0", "tracking", acc["name"], "Pixel/CAPI مش بيبعت أحداث",
                         "أي تحسين هيتبني على داتا ناقصة", "tracking"))
    emq = info.get("emq")
    if emq is not None and emq < th["min_emq"]:
        issues.append(_i("P1", "tracking", acc["name"], f"Event Match Quality = {emq}",
                         "ابعت email/phone hashed + fbp/fbc عبر CAPI عشان الخوارزمية تتعلم أسرع", "tracking"))
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    merged = {}
    for i in issues:
        k = (i["priority"], i["title"])
        if k in merged:
            merged[k]["count"] += 1
            merged[k]["entities"].append(i["entity"])
        else:
            merged[k] = {**i, "count": 1, "entities": [i["entity"]]}
    out = []
    for i in merged.values():
        if i["count"] > 1:
            i["title"] = f"{i['title']} ({i['count']})"
            i["entity"] = "، ".join(i["entities"][:4]) + ("…" if i["count"] > 4 else "")
        out.append(i)
    return sorted(out, key=lambda x: order[x["priority"]])


def _i(priority, area, entity, title, why, owner):
    return {"priority": priority, "area": area, "entity": entity, "title": title, "why": why, "owner": owner}

