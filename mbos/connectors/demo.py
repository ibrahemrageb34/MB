"""Deterministic demo data: 7 fictional accounts, each with a built-in scenario
(healthy, fatigue, CPM spike, prepaid debt, low runway, tracking break, policy issues),
so every part of the system can be seen working without a Meta token.
"""
from __future__ import annotations

import datetime as dt
import math
import random

from ..engine.metrics import result_key
from ..util import today

SCENARIOS = ["healthy", "fatigue", "cpm_spike", "debt", "runway_critical", "tracking_break", "policy"]


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def build(account, idx, days=35):
    rng = random.Random(1000 + idx)
    scen = account.get("demo_scenario") or SCENARIOS[idx % len(SCENARIOS)]
    biz = account["business"]
    obj, aov = biz["objective"], biz.get("aov") or 0
    target = biz.get("target_cpa") or 100
    code = account["code"]
    end = today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    base_cpm = rng.uniform(40, 85)
    base_ctr = rng.uniform(0.009, 0.016)

    formats = ["UGC", "Static", "Carousel", "Video", "Founder"]
    angles = ["Pain", "SocialProof", "Offer", "Transformation", "Demo"]
    hooks = ["Question", "Bold", "Result", "POV", "Price"]

    campaigns, adsets, ads, plan = [], [], [], []
    scale_budget = (biz.get("monthly_budget") or 60000) / 30 * 0.7
    camps = [("SCALE_CBO_" + obj.title() + "_Broad", "scaling", scale_budget),
             ("TEST_ABO_Creative", "testing", None)]
    if obj == "purchase":
        camps.append(("RT_CBO_Purchase_30D", "retargeting", scale_budget * 0.2))
    for ci, (suffix, role, budget) in enumerate(camps):
        cid = f"{code}c{ci}"
        campaigns.append({"id": cid, "name": f"{code}_{suffix}", "status": "ACTIVE", "role": role,
                          "objective": "OUTCOME_SALES", "daily_budget": round(budget) if budget else None})
        n_sets = 2 if role == "testing" else 1
        for si in range(n_sets):
            sid = f"{cid}s{si}"
            learning = "SUCCESS"
            if scen == "policy" and role == "retargeting":
                learning = "LEARNING_LIMITED"
            adsets.append({"id": sid, "name": f"{code}_{role.upper()}_AS{si + 1}", "campaign_id": cid, "status": "ACTIVE",
                           "daily_budget": round(target * (1.5 if si == 0 else 2.2)) if role == "testing" else None,
                           "learning_stage": learning,
                           "audience_type": "retargeting" if role == "retargeting" else "prospecting"})
            n_ads = 3 if role != "scaling" else 5
            for ai in range(n_ads):
                aid = f"{sid}a{ai}"
                f, a, h = formats[(ai + ci + si) % 5], angles[(ai * 2 + idx + si) % 5], hooks[(ai + idx) % 5]
                test = f" | T:T{idx}{si + 1}" if role == "testing" else ""
                name = f"F:{f} | A:{a} | H:{h}{test} | v{ai + 1}"
                if scen == "healthy" and ai == 4:
                    name = f"{code} creative {ai}"  # untagged legacy ad
                q = rng.uniform(0.65, 1.45) if role != "testing" else rng.uniform(0.8, 2.2)
                if a == ("SocialProof" if idx % 2 else "Pain"):
                    q *= 0.8
                if role == "retargeting":
                    q *= 0.7
                ad_start = start + dt.timedelta(days=rng.randint(0, 5) if role != "testing" else days - 8 + si)
                review = "OK"
                if scen == "policy" and ci == 0 and ai == 2:
                    review = "DISAPPROVED"
                ads.append({"id": aid, "name": name, "adset_id": sid, "campaign_id": cid,
                            "status": "ACTIVE", "format": f, "review_status": review,
                            "url_tags": "" if (scen == "policy" and ai == 1) else "utm_source=meta&utm_medium=paid&utm_campaign={{campaign.name}}",
                            "created_time": str(ad_start)})
                plan.append({"ad": ads[-1], "q": q, "start": ad_start, "role": role, "ctr_f": rng.uniform(0.75, 1.35),
                             "hook": rng.uniform(0.18, 0.42) if f in ("UGC", "Video", "Founder") else 0.0,
                             "budget_holder": cid if budget else sid})

    holder_budget = {c["id"]: c["daily_budget"] for c in campaigns if c["daily_budget"]}
    holder_budget.update({a["id"]: a["daily_budget"] for a in adsets if a["daily_budget"]})
    rows, freq7 = [], {}
    fatigue_ad = plan[0]["ad"]["id"]
    for day_i in range(days):
        day = start + dt.timedelta(days=day_i)
        last = day == end
        live = [p for p in plan if p["start"] <= day and p["ad"]["review_status"] != "DISAPPROVED"]
        by_holder = {}
        for p in live:
            by_holder.setdefault(p["budget_holder"], []).append(p)
        for h, ps in by_holder.items():
            weights = [math.exp(-1.6 * p["q"]) for p in ps]
            wsum = sum(weights)
            for p, w in zip(ps, weights):
                spend = holder_budget[h] * (w / wsum) * rng.uniform(0.85, 1.1)
                cpm = base_cpm * rng.uniform(0.9, 1.1) * (1.15 if p["role"] == "retargeting" else 1)
                q, ctr = p["q"], base_ctr * p["ctr_f"]
                if scen == "fatigue" and p["ad"]["id"] == fatigue_ad and day_i > days - 11:
                    decay = 1 - 0.06 * (day_i - (days - 11))
                    ctr *= decay
                    q /= max(decay, 0.35)
                if scen == "cpm_spike" and last:
                    cpm *= 1.8
                    q *= 1.7
                imps = spend / cpm * 1000
                clicks = _poisson(rng, imps * ctr)
                exp_res = spend / (target * q)
                res = _poisson(rng, exp_res)
                if scen == "tracking_break" and last:
                    res = 0
                r = {"date": str(day), "campaign_id": p["ad"]["campaign_id"], "adset_id": p["ad"]["adset_id"],
                     "ad_id": p["ad"]["id"], "spend": round(spend, 2), "impressions": round(imps),
                     "reach": round(imps / rng.uniform(1.1, 1.5)), "clicks": clicks, "lpv": round(clicks * rng.uniform(0.6, 0.85)),
                     "atc": 0, "ic": 0, "purchases": 0, "revenue": 0, "leads": 0, "messages": 0,
                     "video_3s": round(imps * p["hook"]), "thruplay": round(imps * p["hook"] * rng.uniform(0.2, 0.45))}
                key = result_key(obj)
                r[key] = res
                if obj == "purchase":
                    r["revenue"] = round(res * aov * rng.uniform(0.85, 1.2), 2)
                    r["ic"] = round(res * rng.uniform(1.8, 2.6))
                    r["atc"] = round(r["ic"] * rng.uniform(1.8, 2.5))
                rows.append(r)
    for p in plan:
        f = rng.uniform(1.3, 2.4) if p["role"] != "retargeting" else rng.uniform(3, 5)
        if scen == "fatigue" and p["ad"]["id"] == fatigue_ad:
            f = 4.6
        freq7[p["ad"]["id"]] = round(f, 2)

    burn = sum(holder_budget.values())
    balance = {"debt": -round(burn * 0.35), "runway_critical": round(burn * 0.8), "fatigue": round(burn * 2.4)}.get(
        scen, round(burn * rng.uniform(6, 14)))
    info = {"currency": account.get("currency", "EGP"), "account_status": 1, "is_prepay": True,
            "amount_spent": round(rng.uniform(300000, 2_000_000)), "spend_cap": None, "balance_available": balance,
            "emq": 5.4 if scen == "tracking_break" else round(rng.uniform(6.5, 8.8), 1),
            "pixel_ok": True}

    return {"account": account, "as_of": str(end), "info": info, "campaigns": campaigns, "adsets": adsets,
            "ads": ads, "rows": rows, "freq7": freq7, "posts": _posts(rng, account, end),
            "tests": _tests(idx, code, end), "competitors": _competitors(rng, idx, end),
            "journal": _journal(idx, account, end)}


CAPTIONS = [
    ("عرض الأسبوع: خصم 20% على كل المجموعة الجديدة + توصيل مجاني لحد باب البيت. اطلب دلوقتي من اللينك", "Offer"),
    ("آراء عملاءنا بعد شهر استخدام — شوفوا النتيجة بنفسكم", "SocialProof"),
    ("زهقت من المشكلة دي كل يوم؟ الحل أبسط مما تتخيل", "Pain"),
    ("قبل وبعد: الفرق بعد أسبوعين بس", "Transformation"),
    ("ازاي تختار المقاس الصح؟ 3 خطوات بسيطة", "Education"),
    ("كواليس التصوير النهارده 🎬", "General"),
]
COMMENTS_BUY = ["بكام ده؟", "متاح مقاس لارج؟", "عايز اطلب ازاي", "السعر لو سمحت", "التوصيل للإسكندرية؟"]
COMMENTS_SOC = ["جميل جداً", "❤️❤️", "روعة", "منشن لصاحبتي", "تحفة"]


def _posts(rng, account, end):
    posts = []
    now = dt.datetime.combine(end, dt.time(23, 0))
    for i in range(14):
        cap, _ = CAPTIONS[i % len(CAPTIONS)]
        age_h = 60 + i * 50
        reach = rng.randint(3000, 15000)
        posts.append(_post(rng, account, i, now - dt.timedelta(hours=age_h), cap, reach,
                           er=rng.uniform(0.02, 0.05), intent=rng.uniform(0.002, 0.006), buy=rng.randint(0, 2)))
    # new posts (last 48h): one strong, one weak, one too fresh
    posts.append(_post(rng, account, 100, now - dt.timedelta(hours=30), CAPTIONS[0][0], 22000, er=0.085, intent=0.014, buy=4, typ="reel"))
    posts.append(_post(rng, account, 101, now - dt.timedelta(hours=20), CAPTIONS[5][0], 6000, er=0.018, intent=0.001, buy=0))
    posts.append(_post(rng, account, 102, now - dt.timedelta(hours=26), CAPTIONS[3][0], 12000, er=0.045, intent=0.007, buy=2, typ="reel"))
    posts.append(_post(rng, account, 103, now - dt.timedelta(hours=3), CAPTIONS[1][0], 900, er=0.05, intent=0.004, buy=1))
    return posts


def _post(rng, account, i, created, caption, reach, er, intent, buy, typ=None):
    typ = typ or ["image", "reel", "carousel"][i % 3]
    comments = rng.sample(COMMENTS_BUY, min(buy, 5)) + rng.sample(COMMENTS_SOC, 5 - min(buy, 5))
    return {"id": f"{account['code']}p{i}", "platform": "instagram" if i % 2 else "facebook", "type": typ,
            "created_time": created.isoformat(timespec="seconds"), "caption": caption,
            "permalink": None, "reach": reach, "engagements": round(reach * er),
            "shares": round(reach * intent * 0.4), "saves": round(reach * intent * 0.6),
            "video_len_sec": 30 if typ == "reel" else None, "avg_watch_sec": rng.uniform(6, 16) if typ == "reel" else None,
            "comments_sample": comments}


def _tests(idx, code, end):
    return [
        {"id": f"T{idx}1", "start": str(end - dt.timedelta(days=7)), "hypothesis": "هوك بسؤال مباشر عن المشكلة هيرفع CTR ويقلل CPR مقارنة بالهوك العام",
         "variable": "Hook", "angle": "Pain", "format": "UGC", "audience": "Broad", "primary_kpi": "CPR",
         "success": "CPR ≤ 0.9× التارجت مع ≥ 5 نتائج", "failure": "صرف 2× التارجت بدون نتيجة", "owner": "creative"},
        {"id": f"T{idx}2", "start": str(end - dt.timedelta(days=6)), "hypothesis": "عرض التوصيل المجاني هيحوّل أحسن من الخصم بنفس القيمة",
         "variable": "Offer", "angle": "Offer", "format": "Static", "audience": "Broad", "primary_kpi": "CPR",
         "success": "CPR ≤ 0.9× التارجت مع ≥ 5 نتائج", "failure": "صرف 2× التارجت بدون نتيجة", "owner": "media_buyer"},
    ]


def _competitors(rng, idx, end):
    if idx % 3:
        return []
    pages = ["Competitor A", "Competitor B", "Competitor C"]
    texts = ["خصم 30% لفترة محدودة — اطلب دلوقتي", "آراء أكتر من 5000 عميل", "زهقت من الجودة الوحشة؟ جرب",
             "توصيل مجاني لكل المحافظات", "قبل وبعد استخدام المنتج", "خصم 15% على أول طلب"]
    out = []
    for i in range(18):
        out.append({"page": pages[i % 3], "start_date": str(end - dt.timedelta(days=rng.choice([2, 4, 6, 12, 25, 41, 63]))),
                    "is_active": rng.random() > 0.15, "format": rng.choice(["Video", "Static", "Carousel"]),
                    "text": texts[i % len(texts)]})
    return out


def _journal(idx, account, end):
    def ago(n):
        return str(end - dt.timedelta(days=n))
    progress = [3, 3, 2, 1, 0, 0] if idx % 2 else [3, 4, 3, 2, 1, 0]
    from ..engine.roadmap import DEFAULT_PHASES
    phases, t0 = [], 90
    for p, done in zip(DEFAULT_PHASES, progress):
        n = len(p["tasks"])
        status = "done" if done >= n else ("active" if done > 0 else "todo")
        phases.append({"name": p["name"], "status": status, "start": ago(t0), "end": ago(max(t0 - 20, 0)),
                       "tasks": [{"title": t, "done": k < done} for k, t in enumerate(p["tasks"])]})
        t0 -= 18
    events = [
        {"date": ago(88), "type": "milestone", "impact": "neutral", "title": "استلام الأكونت + Audit أولي"},
        {"date": ago(75), "type": "decision", "impact": "positive", "title": "تفعيل CAPI — EMQ من 4.1 لـ 7.2"},
        {"date": ago(60), "type": "decision", "impact": "positive", "title": "دمج 9 ad sets في CBO واحدة Broad"},
        {"date": ago(45), "type": "issue", "impact": "negative", "title": "رفض 3 إعلانات (ادعاءات قبل/بعد)"},
        {"date": ago(30), "type": "result", "impact": "positive", "title": "زاوية SocialProof كسبت — CPR −28%"},
        {"date": ago(14), "type": "issue", "impact": "negative", "title": "توقف الإعلانات يومين — الرصيد خلص"},
        {"date": ago(5), "type": "launch", "impact": "neutral", "title": "إطلاق كامبين Testing أسبوعية"},
    ]
    return {"phases": phases, "events": events}
