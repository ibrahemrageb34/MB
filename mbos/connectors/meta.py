"""Meta Marketing API connector (Graph API, stdlib urllib only).

Token: a System User token with ads_read (+ ads_management for write actions),
pages_read_engagement / instagram_basic / instagram_manage_insights for posts.
Money fields from the API (amount_spent, spend_cap, balance, daily_budget) are in the
currency's minor unit (piasters for EGP) and are converted here.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from ..util import today

ACTION_MAP = {
    "purchases": ["offsite_conversion.fb_pixel_purchase", "omni_purchase", "purchase"],
    "leads": ["lead", "offsite_conversion.fb_pixel_lead", "onsite_conversion.lead_grouped"],
    "messages": ["onsite_conversion.messaging_conversation_started_7d"],
    "lpv": ["landing_page_view"],
    "atc": ["offsite_conversion.fb_pixel_add_to_cart", "omni_add_to_cart", "add_to_cart"],
    "ic": ["offsite_conversion.fb_pixel_initiate_checkout", "omni_initiated_checkout", "initiate_checkout"],
    "video_3s": ["video_view"],
}
BAL_RE = re.compile(r"([-\d.,]+)")


class MetaAPI:
    def __init__(self, cfg):
        m = cfg["meta"]
        self.version = m["api_version"]
        self.token = os.environ.get(m["access_token_env"], "")
        self.windows = m["attribution_windows"]
        self.minor = m.get("currency_minor_unit", 100)
        if not self.token:
            raise RuntimeError(f"Set {m['access_token_env']} (Meta system user token) or run with --demo")

    # ------------------------------------------------------------------ http
    def _url(self, path, params=None):
        params = dict(params or {})
        params["access_token"] = self.token
        return f"https://graph.facebook.com/{self.version}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"

    def get(self, path, params=None, retries=3):
        url = self._url(path, params)
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")
                if e.code in (429, 500, 503) or '"code":17' in body or '"code":4' in body:
                    time.sleep(2 ** (attempt + 2))  # rate limit / transient
                    continue
                raise RuntimeError(f"Meta API {e.code}: {body[:400]}") from None
        raise RuntimeError(f"Meta API: gave up after {retries} retries on {path}")

    def paged(self, path, params=None, limit_pages=50):
        out, data = [], self.get(path, params)
        for _ in range(limit_pages):
            out.extend(data.get("data", []))
            nxt = data.get("paging", {}).get("next")
            if not nxt:
                break
            with urllib.request.urlopen(nxt, timeout=60) as r:
                data = json.loads(r.read())
        return out

    def post(self, path, params):
        params = dict(params)
        params["access_token"] = self.token
        req = urllib.request.Request(f"https://graph.facebook.com/{self.version}/{path.lstrip('/')}",
                                     data=urllib.parse.urlencode(params).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    # ------------------------------------------------------------------ fetch
    def fetch(self, account, days=35):
        act = account["id"] if account["id"].startswith("act_") else f"act_{account['id']}"
        end = today() - dt.timedelta(days=1)
        start = end - dt.timedelta(days=days - 1)
        info = self.account_info(act, account)
        return {
            "account": account,
            "as_of": str(end),
            "info": info,
            "campaigns": self.campaigns(act),
            "adsets": self.adsets(act),
            "ads": self.ads(act),
            "rows": self.insights(act, start, end),
            "freq7": self.freq7(act, end),
            "posts": self.posts(account),
        }

    def account_info(self, act, account):
        j = self.get(act, {"fields": "name,currency,account_status,amount_spent,spend_cap,balance,"
                                     "is_prepay_account,funding_source_details,timezone_name"})
        amount_spent = float(j.get("amount_spent", 0)) / self.minor
        spend_cap = float(j["spend_cap"]) / self.minor if j.get("spend_cap") not in (None, "0") else None
        available = None
        fsd = j.get("funding_source_details") or {}
        m = BAL_RE.search(fsd.get("display_string", "") or "")
        if m and j.get("is_prepay_account"):
            try:
                available = float(m.group(1).replace(",", ""))
            except ValueError:
                available = None
        owed = float(j.get("balance", 0) or 0) / self.minor
        if available is None and j.get("is_prepay_account") and owed > 0:
            available = -owed  # prepaid account carrying an unpaid balance = debt
        manual = (account.get("prepaid") or {}).get("manual_balance")
        if manual is not None:
            available = float(manual)
        return {"currency": j.get("currency", "EGP"), "account_status": j.get("account_status"),
                "amount_spent": amount_spent, "spend_cap": spend_cap, "is_prepay": bool(j.get("is_prepay_account")),
                "balance_available": available, "funding_display": fsd.get("display_string"),
                "emq": (account.get("tracking") or {}).get("emq"),
                "pixel_ok": (account.get("tracking") or {}).get("pixel_ok")}

    def campaigns(self, act):
        rows = self.paged(f"{act}/campaigns", {"fields": "id,name,effective_status,objective,daily_budget,bid_strategy",
                                               "limit": 200})
        return [{"id": c["id"], "name": c["name"], "status": c.get("effective_status"),
                 "objective": c.get("objective"), "bid_strategy": c.get("bid_strategy"),
                 "daily_budget": float(c["daily_budget"]) / self.minor if c.get("daily_budget") else None,
                 "role": _role(c["name"])} for c in rows]

    def adsets(self, act):
        rows = self.paged(f"{act}/adsets", {"fields": "id,name,campaign_id,effective_status,daily_budget,"
                                                      "optimization_goal,learning_stage_info", "limit": 200})
        return [{"id": a["id"], "name": a["name"], "campaign_id": a["campaign_id"], "status": a.get("effective_status"),
                 "daily_budget": float(a["daily_budget"]) / self.minor if a.get("daily_budget") else None,
                 "learning_stage": (a.get("learning_stage_info") or {}).get("status"),
                 "audience_type": "retargeting" if re.search(r"\b(RT|RMK|retarget)", a["name"], re.I) else "prospecting"}
                for a in rows]

    def ads(self, act):
        rows = self.paged(f"{act}/ads", {"fields": "id,name,adset_id,campaign_id,effective_status,created_time,"
                                                   "creative{id,object_type,url_tags,thumbnail_url,effective_object_story_id},"
                                                   "ad_review_feedback", "limit": 200})
        out = []
        for a in rows:
            cr = a.get("creative") or {}
            review = "DISAPPROVED" if a.get("effective_status") == "DISAPPROVED" else (
                "WITH_ISSUES" if a.get("effective_status") == "WITH_ISSUES" else "OK")
            out.append({"id": a["id"], "name": a["name"], "adset_id": a["adset_id"], "campaign_id": a["campaign_id"],
                        "status": a.get("effective_status"), "created_time": a.get("created_time"),
                        "format": {"VIDEO": "Video", "PHOTO": "Static", "SHARE": "Link"}.get(cr.get("object_type"), cr.get("object_type")),
                        "url_tags": cr.get("url_tags"), "thumb": cr.get("thumbnail_url"),
                        "post_id": cr.get("effective_object_story_id"), "review_status": review})
        return out

    def insights(self, act, start, end):
        fields = ("date_start,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,spend,impressions,reach,"
                  "inline_link_clicks,actions,action_values,video_thruplay_watched_actions")
        rows = self.paged(f"{act}/insights", {
            "level": "ad", "time_increment": 1, "fields": fields, "limit": 500,
            "time_range": json.dumps({"since": str(start), "until": str(end)}),
            "action_attribution_windows": json.dumps(self.windows),
        })
        out = []
        for r in rows:
            acts = {a["action_type"]: float(a["value"]) for a in r.get("actions", [])}
            vals = {a["action_type"]: float(a["value"]) for a in r.get("action_values", [])}
            row = {"date": r["date_start"], "campaign_id": r["campaign_id"], "adset_id": r["adset_id"],
                   "ad_id": r["ad_id"], "spend": float(r.get("spend", 0)), "impressions": float(r.get("impressions", 0)),
                   "reach": float(r.get("reach", 0)), "clicks": float(r.get("inline_link_clicks", 0))}
            for k, types in ACTION_MAP.items():
                row[k] = next((acts[t] for t in types if t in acts), 0.0)
            row["revenue"] = next((vals[t] for t in ACTION_MAP["purchases"] if t in vals), 0.0)
            row["thruplay"] = sum(float(a["value"]) for a in r.get("video_thruplay_watched_actions", []))
            out.append(row)
        return out

    def freq7(self, act, end):
        start = end - dt.timedelta(days=6)
        rows = self.paged(f"{act}/insights", {"level": "ad", "fields": "ad_id,frequency", "limit": 500,
                                              "time_range": json.dumps({"since": str(start), "until": str(end)})})
        return {r["ad_id"]: float(r.get("frequency", 0)) for r in rows}

    def posts(self, account, limit=30):
        out = []
        ig = account.get("ig_user_id")
        if ig:
            media = self.paged(f"{ig}/media", {"fields": "id,caption,media_type,media_product_type,timestamp,permalink,"
                                                         "like_count,comments_count,comments.limit(25){text}",
                                               "limit": limit}, limit_pages=1)
            for m in media:
                ins = {}
                try:
                    metrics = "reach,saved,shares,total_interactions,views"
                    if m.get("media_product_type") == "REELS":
                        metrics += ",ig_reels_avg_watch_time"
                    for x in self.get(f"{m['id']}/insights", {"metric": metrics}).get("data", []):
                        ins[x["name"]] = x["values"][0]["value"] if x.get("values") else x.get("total_value", {}).get("value")
                except RuntimeError:
                    pass  # metric set changes between API versions; keep the post with partial data
                out.append({"id": m["id"], "platform": "instagram",
                            "type": "reel" if m.get("media_product_type") == "REELS" else m.get("media_type", "").lower(),
                            "created_time": m["timestamp"][:19], "caption": m.get("caption", ""), "permalink": m.get("permalink"),
                            "reach": ins.get("reach") or 0, "engagements": ins.get("total_interactions") or
                            (m.get("like_count", 0) + m.get("comments_count", 0)),
                            "shares": ins.get("shares") or 0, "saves": ins.get("saved") or 0,
                            "avg_watch_sec": (ins.get("ig_reels_avg_watch_time") or 0) / 1000,
                            "comments_sample": [c["text"] for c in (m.get("comments") or {}).get("data", [])]})
        return out

    # ------------------------------------------------------------------ write (explicit only)
    def set_spend_cap(self, act, amount):
        return self.post(act, {"spend_cap": int(round(amount * self.minor))})

    def set_daily_budget(self, object_id, amount):
        return self.post(object_id, {"daily_budget": int(round(amount * self.minor))})

    def pause(self, object_id):
        return self.post(object_id, {"status": "PAUSED"})


def _role(name):
    n = name.upper()
    if "TEST" in n:
        return "testing"
    if re.search(r"\b(RT|RMK|RETARGET)", n):
        return "retargeting"
    return "scaling"
