"""Prepaid wallet: runway, top-up plan and a debt guard.

Why accounts go into debt on prepaid: Meta charges delivered impressions with a lag
and budgets are daily *targets*, so the account can deliver past the remaining
funds before it is stopped. Defences, in order of reliability:
  1. Top up before the runway ends (forecast + alert)          -> runway / topup_plan
  2. Account spending limit (spend_cap) just below the funds    -> spend_cap_guard
  3. Scale only when the runway allows it                        -> used by budget.py
"""
from __future__ import annotations

import datetime as dt

from ..util import d, mean
from . import metrics as M


def burn_rate(bundle):
    """Conservative daily burn: max(recent 3-day avg, sum of active daily budgets)."""
    end = d(bundle["as_of"])
    rows = M.window(bundle["rows"], end, 3)
    by_day = M.daily(rows)
    recent = mean([v["spend"] for v in by_day.values()]) if by_day else 0.0
    budgets = 0.0
    active_camps = {c["id"] for c in bundle["campaigns"] if c.get("status") == "ACTIVE"}
    for c in bundle["campaigns"]:
        if c["id"] in active_camps and c.get("daily_budget"):
            budgets += c["daily_budget"]
    for a in bundle["adsets"]:
        if a["campaign_id"] in active_camps and a.get("status") == "ACTIVE" and a.get("daily_budget"):
            budgets += a["daily_budget"]
    return max(recent, budgets), recent, budgets


def analyze(bundle, cfg):
    p = cfg["prepaid"]
    info = bundle["info"]
    burn, recent, scheduled = burn_rate(bundle)
    bal = info.get("balance_available")
    res = {"is_prepay": info.get("is_prepay", True), "balance": bal, "burn_rate": burn,
           "recent_spend": recent, "scheduled_budget": scheduled, "currency": info.get("currency", "EGP")}
    if bal is None:
        res.update(status="unknown", runway_days=None,
                   message="الرصيد المتاح غير معروف — أدخل manual_balance في الإعدادات أو اربط funding_source_details")
        return res

    runway = bal / burn if burn > 0 else None
    res["runway_days"] = runway
    if bal < 0:
        status = "debt"
    elif runway is not None and runway < p["critical_days"]:
        status = "critical"
    elif runway is not None and runway < p["warning_days"]:
        status = "warning"
    else:
        status = "ok"
    res["status"] = status

    as_of = d(bundle["as_of"])
    if runway is not None:
        res["depletion_date"] = str(as_of + dt.timedelta(days=max(runway, 0)))
    # Top-up so the account is covered for target_cover_days at the current burn.
    need = burn * p["target_cover_days"] - bal
    res["topup_recommended"] = max(0.0, round(need / 100) * 100) if burn else 0.0
    # Data ends yesterday; today's spend is already burning the balance.
    today_ = as_of + dt.timedelta(days=1)
    days_after_today = (runway or 0) - 1 - p["lead_time_days"]
    res["topup_by"] = str(today_ + dt.timedelta(days=max(0, int(days_after_today))))
    res["topup_now"] = days_after_today < 1

    # Debt guard: set the account spending limit just below what is actually funded.
    amount_spent = info.get("amount_spent")
    if amount_spent is not None:
        buffer = burn * p["spend_cap_buffer_days"]
        res["spend_cap_recommended"] = max(amount_spent, amount_spent + max(bal, 0) - buffer)
        res["spend_cap_current"] = info.get("spend_cap")

    res["message"] = {
        "debt": f"الأكونت عليه مديونية {abs(bal):,.0f} — الإعلانات هتقف. سدّد المديونية + شحن {res['topup_recommended']:,.0f} وفعّل حد الإنفاق.",
        "critical": f"الرصيد يكفي {runway:.1f} يوم بس — اشحن النهارده ({res['topup_recommended']:,.0f}) وثبّت حد إنفاق.",
        "warning": f"الرصيد يكفي {runway:.1f} يوم — جهّز شحن قبل {res['topup_by']}.",
        "ok": f"الرصيد يكفي {runway:.1f} يوم." if runway is not None else "مفيش صرف حالي.",
    }[status]
    return res


def treasury(prepaid_by_account, horizon_days=7):
    """Portfolio cash plan: how much money each account needs over the horizon."""
    rows = []
    for name, p in prepaid_by_account.items():
        burn = p.get("burn_rate") or 0
        bal = p.get("balance") or 0
        need = max(0.0, burn * horizon_days - bal)
        rows.append({"account": name, "status": p.get("status"), "runway_days": p.get("runway_days"),
                     "need_next_7d": need, "topup_by": p.get("topup_by"), "currency": p.get("currency")})
    order = {"debt": 0, "critical": 1, "warning": 2, "unknown": 3, "ok": 4}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["runway_days"] if r["runway_days"] is not None else 1e9))
    return {"rows": rows, "total_need_next_7d": sum(r["need_next_7d"] for r in rows)}
