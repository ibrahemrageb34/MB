"""Optional Claude layer: qualitative creative analysis of new posts (hook, angle, offer,
objections, CTA) in Egyptian Arabic. The rule-based scores work without it; this adds the
"why" a creative strategist would write. Uses the Messages API over urllib (no SDK needed).
"""
from __future__ import annotations

import json
import os
import urllib.request

PROMPT = """أنت Creative Strategist لحسابات Meta Ads في السوق المصري.
البراند: {brand} ({vertical}) — الهدف: {objective} — التارجت CPA: {target}.
بوست جديد نزل على {platform} ({type}):
الكابشن: {caption}
عينة كومنتات: {comments}
مؤشرات عضوية: وصول {reach}، تفاعل {er:.1%}.

حلّل البوست كإعلان محتمل. رد بـ JSON فقط بالمفاتيح:
hook (أول 3 ثواني/أول سطر وقوته), angle, desire_or_pain, proof, offer, cta, objections (قائمة),
funnel_stage (TOFU/MOFU/BOFU), ad_potential (high/medium/low), why (جملتين), improve (أهم تعديل واحد قبل ما يتحول لإعلان).
"""


def enabled(cfg):
    return cfg["ai"]["enabled"] and bool(os.environ.get(cfg["ai"]["api_key_env"]))


def analyze_post(cfg, account, post):
    key = os.environ.get(cfg["ai"]["api_key_env"])
    biz = account["business"]
    er = (post.get("engagements", 0) / post["reach"]) if post.get("reach") else 0
    msg = PROMPT.format(brand=account["name"], vertical=biz.get("vertical", ""), objective=biz["objective"],
                        target=biz["target_cpa"], platform=post.get("platform"), type=post.get("type"),
                        caption=post.get("caption", "")[:1500], comments=" | ".join(post.get("comments_sample", [])[:15]),
                        reach=post.get("reach"), er=er)
    body = {"model": cfg["ai"]["model"], "max_tokens": 1200, "messages": [{"role": "user", "content": msg}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            text = "".join(b.get("text", "") for b in json.loads(r.read())["content"])
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1])
    except Exception as e:  # AI is an enhancement; never break the daily run because of it
        return {"error": str(e)[:200]}


TAG_PROMPT = """صنّف كل إعلان من إعلانات Meta دي للبراند {brand} ({vertical}).
لكل إعلان رجّع:
- format: واحد من {formats} (حسب نوع الكريتيف: {fmt_hint})
- angle: واحد من Pain, Desire, SocialProof, Offer, Transformation, Demo, Education, Comparison, Objection, Urgency, Trust, Brand
- hook: واحد من Question, Bold, Result, POV, Price, Problem, Story, Statement
- offer: العرض لو موجود بكلمة واحدة (FreeShip, Discount, Bundle, Gift, Installments, None)

الإعلانات (id: نوع | النص):
{ads}

رد بـ JSON فقط: {{"<id>": {{"format": "...", "angle": "...", "hook": "...", "offer": "..."}}}}
"""


def _call(cfg, msg, max_tokens=2000):
    key = os.environ.get(cfg["ai"]["api_key_env"])
    body = {"model": cfg["ai"]["model"], "max_tokens": max_tokens, "messages": [{"role": "user", "content": msg}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = "".join(b.get("text", "") for b in json.loads(r.read())["content"])
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def tag_ads(cfg, account, ads, batch=20):
    """{ad_id: {format, angle, hook, offer}} for ads without naming-convention tags.
    Tags come from the ad copy, so they are an estimate; the naming convention still wins."""
    out = {}
    for i in range(0, len(ads), batch):
        chunk = ads[i:i + batch]
        lines = "\n".join(f"{a['id']}: {a.get('format') or '?'} | {a.get('text', '')[:400]}" for a in chunk)
        msg = TAG_PROMPT.format(brand=account["name"], vertical=account["business"].get("vertical", ""),
                                formats=", ".join(cfg["creative"]["formats"]),
                                fmt_hint="Video/Static/Carousel من البيانات", ads=lines)
        try:
            res = _call(cfg, msg)
        except Exception:
            continue  # tagging is best-effort; untagged ads still get analysed
        ids = {a["id"] for a in chunk}
        out.update({k: {**v, "source": "ai"} for k, v in res.items() if k in ids and isinstance(v, dict)})
    return out
