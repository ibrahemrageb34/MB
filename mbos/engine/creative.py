"""Creative analytics, fatigue detection, new-post triage and test-idea generation.

Format (UGC, Static, Carousel...) and Angle (Pain, SocialProof, Offer...) are kept as
separate dimensions on purpose: a winning angle can be re-shot in a new format, and a
winning format with a weak angle is still a weak ad.
"""
from __future__ import annotations

import datetime as dt

from ..util import d, div, median, parse_tags
from . import metrics as M

ANGLES_KW = {
    "Offer": ["خصم", "عرض", "%", "off", "sale", "هدية", "مجاني", "free", "كود", "توصيل مجاني"],
    "SocialProof": ["عملاء", "تقييم", "ريفيو", "review", "آراء", "رأي", "قالوا", "الأكثر مبيع"],
    "Pain": ["مشكلة", "تعبت", "زهقت", "بتعاني", "خايف", "مش لاقي", "وجع", "problem"],
    "Transformation": ["قبل", "بعد", "before", "after", "النتيجة", "اتغير"],
    "Demo": ["ازاي", "طريقة", "شوف", "تجربة", "unboxing", "how to", "استخدام"],
    "Education": ["نصيحة", "نصايح", "تعرف", "معلومة", "خطوات", "tips", "دليل"],
    "Urgency": ["آخر", "لفترة محدودة", "النهارده بس", "الكمية محدودة", "limited", "ينتهي"],
}
INTENT_KW = ["بكام", "السعر", "سعر", "متاح", "متوفر", "اطلب", "عايز", "عاوز", "ازاي اطلب", "التوصيل",
             "مقاس", "لون", "الفرع", "العنوان", "price", "how much", "available", "order", "dm", "واتس"]
OFFER_KW = ["جنيه", "ج.م", "egp", "خصم", "%", "اطلب", "احجز", "سجل", "لينك", "link", "رقم", "واتساب"]


# --------------------------------------------------------------------------- analytics
def ad_table(bundle, days=14):
    acc = bundle["account"]
    obj = acc["business"]["objective"]
    end = d(bundle["as_of"])
    rows = M.window(bundle["rows"], end, days)
    by_ad = M.group(rows, "ad_id", obj)
    early = M.group([r for r in rows if d(r["date"]) <= end - dt.timedelta(days=4)], "ad_id", obj)
    late = M.group(M.window(rows, end, 3), "ad_id", obj)
    ads = {a["id"]: a for a in bundle["ads"]}
    out = []
    for ad_id, m in by_ad.items():
        a = ads.get(ad_id, {"name": ad_id})
        tags = parse_tags(a.get("name", ""))
        tags.setdefault("format", a.get("format", "Unknown"))
        tags.setdefault("angle", "Untagged")
        tags.setdefault("hook", "Untagged")
        e, l = early.get(ad_id), late.get(ad_id)
        ctr_decay = None
        if e and l and e["ctr"] and l["ctr"] is not None and e["impressions"] > 2000 and l["impressions"] > 1000:
            ctr_decay = (l["ctr"] - e["ctr"]) / e["ctr"]
        out.append({"ad_id": ad_id, "name": a.get("name"), "status": a.get("status"),
                    "campaign_id": a.get("campaign_id"), "thumb": a.get("thumb"), **tags,
                    "spend": m["spend"], "results": m["results"], "cpr": m["cpr"], "ctr": m["ctr"],
                    "hook_rate": m["hook_rate"], "hold_rate": m["hold_rate"], "cvr": m["cvr"],
                    "roas": m["roas"], "freq7": bundle["freq7"].get(ad_id), "ctr_decay": ctr_decay})
    out.sort(key=lambda x: -x["spend"])
    return out


def by_dimension(table, dim, target, min_spend):
    groups = {}
    for r in table:
        g = groups.setdefault(r.get(dim) or "Untagged", {"spend": 0.0, "results": 0.0, "ads": 0, "winners": 0,
                                                          "hook": [], "ctr": []})
        g["spend"] += r["spend"]
        g["results"] += r["results"]
        g["ads"] += 1
        if r["cpr"] is not None and r["cpr"] <= target and r["spend"] >= min_spend:
            g["winners"] += 1
        if r["hook_rate"] is not None:
            g["hook"].append(r["hook_rate"])
        if r["ctr"] is not None:
            g["ctr"].append(r["ctr"])
    total_spend = sum(g["spend"] for g in groups.values()) or 1
    out = []
    for k, g in groups.items():
        out.append({"value": k, "spend": g["spend"], "spend_share": g["spend"] / total_spend,
                    "results": g["results"], "cpr": div(g["spend"], g["results"]), "ads": g["ads"],
                    "win_rate": div(g["winners"], g["ads"], 0), "hook_rate": median(g["hook"], None),
                    "ctr": median(g["ctr"], None)})
    out.sort(key=lambda x: (x["cpr"] is None, x["cpr"] or 0))
    return out


def fatigue(table, cfg):
    th = cfg["thresholds"]
    out = []
    for r in table:
        if r["status"] != "ACTIVE":
            continue
        f = r["freq7"] or 0
        dec = r["ctr_decay"]
        if dec is not None and dec <= -th["fatigue_ctr_drop"] and f >= th["fatigue_min_frequency"]:
            out.append({**r, "reason": f"CTR نزل {abs(dec) * 100:.0f}% مع Frequency {f:.1f}"})
    return out


def insights(bundle, cfg, table):
    """Plain-language findings for the creative team (what to make more / less of)."""
    biz = bundle["account"]["business"]
    target = biz["target_cpa"]
    min_spend = cfg["thresholds"]["min_spend_x_cpa_for_verdict"] * target
    dims = {k: by_dimension(table, k, target, min_spend) for k in ("angle", "format", "hook", "offer")}
    notes = []

    def qualified(rows):
        return [x for x in rows if x["spend"] >= min_spend and x["cpr"] is not None and x["value"] != "Untagged"]

    for dim, label in (("angle", "الزاوية"), ("format", "الفورمات"), ("hook", "نوع الهوك")):
        q = qualified(dims[dim])
        if len(q) >= 2:
            best, worst = q[0], q[-1]
            if worst["cpr"] > best["cpr"] * 1.25:
                notes.append({"type": "double_down", "dim": dim,
                              "text": f"{label} «{best['value']}» أرخص {(1 - best['cpr'] / worst['cpr']) * 100:.0f}% من «{worst['value']}» "
                                      f"(CPR {best['cpr']:,.0f} مقابل {worst['cpr']:,.0f}). زوّد إنتاج «{best['value']}» وقلّل «{worst['value']}»."})
        if q and q[0]["spend_share"] < 0.25 and len(q) > 1:
            notes.append({"type": "under_funded", "dim": dim,
                          "text": f"{label} «{q[0]['value']}» الأفضل بس واخد {q[0]['spend_share'] * 100:.0f}% بس من الصرف — "
                                  f"محتاج نسخ أكتر منه عشان الخوارزمية تصرف عليه."})
    for r in table:
        if r["hook_rate"] and r["hook_rate"] >= 0.35 and r["cvr"] is not None and r["spend"] >= min_spend:
            avg_cvr = median([x["cvr"] for x in table if x["cvr"] is not None])
            if r["cvr"] < 0.6 * avg_cvr:
                notes.append({"type": "message_mismatch",
                              "text": f"«{r['name']}» بيشد الانتباه (Hook {r['hook_rate'] * 100:.0f}%) بس التحويل ضعيف — "
                                      "غالباً الوعد في الإعلان مش هو اللي في صفحة الهبوط/العرض. راجع الـ message match."})
    untagged = sum(r["spend"] for r in table if r.get("angle") == "Untagged")
    tot = sum(r["spend"] for r in table) or 1
    if untagged / tot > 0.3:
        notes.append({"type": "hygiene",
                      "text": f"{untagged / tot * 100:.0f}% من الصرف على إعلانات من غير tags في الاسم — التحليل ده أعمى عليها. طبّق docs/NAMING.md."})
    return {"dimensions": dims, "notes": notes}


# --------------------------------------------------------------------------- new posts
def classify_angle(text):
    t = (text or "").lower()
    scores = {k: sum(1 for w in kws if w.lower() in t) for k, kws in ANGLES_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"


def triage_posts(bundle, cfg, table, budget_recs):
    """Score each new organic post and decide: skip / test / add to existing campaign."""
    acc = bundle["account"]
    biz = acc["business"]
    th = cfg["post_triage"]
    now = dt.datetime.combine(d(bundle["as_of"]), dt.time(23, 59))
    posts = bundle.get("posts", [])
    history = [p for p in posts if p.get("reach")]
    base_er = median([div(p["engagements"], p["reach"], 0) for p in history], 0.0) or 0.01
    base_intent = median([div(p.get("shares", 0) + p.get("saves", 0), p["reach"], 0) for p in history], 0.0) or 0.001

    angle_rank = [x["value"] for x in by_dimension(table, "angle", biz["target_cpa"], 0) if x["cpr"] is not None]
    camp_by_id = {c["id"]: c for c in bundle["campaigns"]}
    role_of = {c["id"]: c.get("role") for c in bundle["campaigns"]}
    role_of.update({a["id"]: role_of.get(a["campaign_id"]) for a in bundle["adsets"]})
    scaling = [r for r in budget_recs if r["action"] in ("scale", "hold") and r["cpr7"] is not None
               and r["cpr7"] <= biz["target_cpa"] and role_of.get(r["id"]) == "scaling"]
    testing_camp = next((c for c in bundle["campaigns"] if c.get("role") == "testing" and c.get("status") == "ACTIVE"), None)

    out = []
    for p in posts:
        created = dt.datetime.fromisoformat(p["created_time"][:19])
        age_h = (now - created).total_seconds() / 3600
        if age_h > th["new_post_hours"]:
            continue
        reach = p.get("reach") or 0
        er = div(p.get("engagements", 0), reach, 0)
        intent = div(p.get("shares", 0) + p.get("saves", 0), reach, 0)
        comments = p.get("comments_sample", [])
        buy_comments = sum(1 for c in comments if any(k in c.lower() for k in INTENT_KW))
        caption = p.get("caption", "")
        angle = p.get("angle") or classify_angle(caption)

        s_er = min(35, 35 * div(er, base_er, 0) / 2)
        s_int = min(25, 25 * div(intent, base_intent, 0) / 2)
        s_buy = min(20, 20 * div(buy_comments, max(len(comments), 1), 0) / 0.3)
        if p.get("type") in ("video", "reel") and p.get("video_len_sec"):
            s_ret = min(10, 10 * div(p.get("avg_watch_sec", 0), p["video_len_sec"], 0) / 0.4)
        else:
            s_ret = 5
        s_offer = 10 if any(k in caption.lower() for k in OFFER_KW) else 3
        score = round(s_er + s_int + s_buy + s_ret + s_offer)

        why = [f"Engagement {er * 100:.1f}% (متوسط الصفحة {base_er * 100:.1f}%)",
               f"Share+Save {intent * 100:.2f}% (متوسط {base_intent * 100:.2f}%)",
               f"{buy_comments}/{len(comments)} كومنتات فيها نية شراء"]
        if age_h < th["min_hours_for_verdict"] or reach < th["min_reach"]:
            verdict, route, how = "wait", "—", f"البوست عمره {age_h:.0f} ساعة/وصول {reach:,} — نعيد التقييم بعد {th['min_hours_for_verdict']} ساعة."
        elif score >= th["promote_score"]:
            verdict = "promote"
            if angle in angle_rank[:2] and scaling:
                target_camp = camp_by_id.get(scaling[0]["id"]) or {"name": scaling[0]["name"]}
                route = "existing"
                how = (f"الزاوية «{angle}» من أفضل الزوايا في الأكونت → أضفه كإعلان جديد بالـ Post ID (عشان تحتفظ بالـ social proof) "
                       f"جوه «{target_camp['name']}». متغيرش الميزانية في نفس اليوم.")
            else:
                route = "test"
                how = (f"زاوية «{angle}» مش مثبتة في الأكونت → اختبرها في «{testing_camp['name'] if testing_camp else 'كامبين الاختبار'}» "
                       f"بـ ad set مستقل وميزانية {th['test_budget_x_cpa'] * biz['target_cpa']:,.0f}/يوم لمدة 3 أيام. "
                       "لو كسب يتنقل للسكيل بنفس الـ Post ID.")
        elif score >= th["test_score"]:
            verdict, route = "test", "test"
            how = (f"أداء عضوي متوسط — اختبار صغير في كامبين الاختبار بحد صرف {th['kill_spend_x_cpa']}× التارجت CPA "
                   f"({th['kill_spend_x_cpa'] * biz['target_cpa']:,.0f}). لو مجابش نتيجة يتقفل.")
        else:
            verdict, route = "skip", "—"
            how = "يفضل عضوي بس. الأداء أقل من متوسط الصفحة ومفيش نية شراء واضحة."
        out.append({"id": p["id"], "platform": p.get("platform"), "type": p.get("type"), "created_time": p["created_time"],
                    "caption": caption[:180], "permalink": p.get("permalink"), "angle": angle, "score": score,
                    "verdict": verdict, "route": route, "how": how, "why": why, "age_h": round(age_h),
                    "reach": reach, "ai": p.get("ai")})
    out.sort(key=lambda x: -x["score"])
    return out


# --------------------------------------------------------------------------- ideas
def test_ideas(bundle, cfg, table, ins, fatigued, comp=None):
    """Structured hypotheses (not random ads): combine what already works with what is untested."""
    dims = ins["dimensions"]
    target = bundle["account"]["business"]["target_cpa"]
    ideas = []
    angles = [x for x in dims["angle"] if x["cpr"] is not None and x["value"] != "Untagged"]
    formats = [x for x in dims["format"] if x["value"] != "Unknown"]
    tested = {(r.get("angle"), r.get("format")) for r in table}
    all_formats = cfg["creative"]["formats"]
    if angles:
        best = angles[0]["value"]
        for f in all_formats:
            if (best, f) not in tested:
                ideas.append(_idea(f"الزاوية الكسبانة «{best}» بفورمات {f}",
                                   f"لو «{best}» بيكسب كرسالة، هيكسب كمان بفورمات {f} ويوصل لشريحة مختلفة داخل نفس الجمهور",
                                   "Format", best, f, target))
                if len(ideas) >= 2:
                    break
    hooks = [x for x in dims["hook"] if x["hook_rate"] is not None and x["value"] != "Untagged"]
    if hooks and angles:
        hk = max(hooks, key=lambda x: x["hook_rate"])["value"]
        for a in angles[1:3]:
            ideas.append(_idea(f"هوك «{hk}» على زاوية «{a['value']}»",
                               f"الهوك «{hk}» أعلى Hook rate — تركيبه على زاوية «{a['value']}» ممكن يحسّن CTR بتاعها",
                               "Hook", a["value"], formats[0]["value"] if formats else "UGC", target))
    for f in fatigued[:2]:
        ideas.append(_idea(f"بديل لـ «{f['name']}» (إرهاق)",
                           "نفس الزاوية والعرض بهوك جديد وأول 3 ثواني مختلفين — بنختبر إن المشكلة في التكرار مش في الرسالة",
                           "Hook", f.get("angle"), f.get("format"), target))
    if comp:
        for w in comp.get("long_runners", [])[:1]:
            ideas.append(_idea(f"زاوية المنافس «{w['angle']}» ({w['page']})",
                               f"إعلان المنافس شغال بقاله {w['days']} يوم — غالباً مربح. نختبر نفس الزاوية بعرضنا وبراندنا (مش نسخ)",
                               "Angle", w["angle"], w.get("format") or "Static", target))
    return ideas[:6]


def _idea(title, hypothesis, variable, angle, fmt, target):
    return {"title": title, "hypothesis": hypothesis, "variable": variable, "angle": angle, "format": fmt,
            "primary_kpi": "CPR", "budget": f"{2 * target:,.0f} لكل إعلان على 3-4 أيام",
            "success": "CPR ≤ 0.9× التارجت مع ≥ 5 نتائج", "failure": "صرف 2× التارجت بدون نتيجة أو CPR ≥ 1.5×"}

