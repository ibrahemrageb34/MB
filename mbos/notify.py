"""Alerts: Telegram (direct) and a generic JSON webhook (n8n -> WhatsApp/Slack/Email)."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


def telegram(cfg, text):
    n = cfg["notifications"]
    token, chat = os.environ.get(n["telegram_bot_token_env"]), os.environ.get(n["telegram_chat_id_env"])
    if not (token and chat):
        return False
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)]:
        data = urllib.parse.urlencode({"chat_id": chat, "text": chunk, "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30).read()
    return True


def webhook(cfg, payload):
    url = os.environ.get(cfg["notifications"]["webhook_url_env"])
    if not url:
        return False
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False, default=str).encode(),
                                 headers={"content-type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    return True


def alert_items(results, portfolio, kind="all"):
    """[(dedupe_key, text)] — the key stays stable while the numbers in the text move,
    so a wallet alert repeats only when its status or deadline changes."""
    lines = []
    if kind in ("all", "prepaid"):
        for t in portfolio["treasury"]["rows"]:
            if t["status"] in ("debt", "critical", "warning"):
                icon = {"debt": "⛔", "critical": "🔴", "warning": "🟡"}[t["status"]]
                if t["status"] == "debt":
                    state = "عليه مديونية والإعلانات هتقف"
                else:
                    state = f"الرصيد يكفي {t['runway_days']:.1f} يوم" if t["runway_days"] is not None else "الرصيد غير معروف"
                lines.append((f"prepaid|{t['account']}|{t['status']}|{t['topup_by']}",
                              f"{icon} {t['account']}: {state} — محتاج {t['need_next_7d']:,.0f} {t['currency']} قبل {t['topup_by']}"))
    if kind in ("all", "anomaly"):
        for r in results:
            for a in r["anomalies"]:
                if a["severity"] == "critical":
                    lines.append((f"anomaly|{r['as_of']}|{r['name']}|{a['entity']}|{a['metric']}",
                                  f"🔴 {r['name']} · {a['entity']}: {a['metric_ar']} {a['change'] * 100:+.0f}% — {a['hint']}"))
    if kind in ("all", "posts"):
        for r in results:
            for p in r["posts"]:
                if p["verdict"] in ("promote", "test"):
                    tag = "🚀 يستحق إعلان" if p["verdict"] == "promote" else "🧪 يستحق اختبار"
                    lines.append((f"post|{p['id']}|{p['verdict']}",
                                  f"{tag} · {r['name']} · Score {p['score']} · {p['angle']}\n   «{p['caption'][:70]}»\n   ← {p['how']}"))
    return lines
