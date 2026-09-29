"""Business results the ad platform cannot see: showroom / WhatsApp / offline sales,
qualified leads and closed deals. The team fills a Google Sheet (or CSV); the engine joins
it with ad spend per brand to get the numbers that actually matter:

  MER  = all sales ÷ all ad spend           (what "600k sales on 30k spend" means)
  CPQL = ad spend ÷ qualified leads
  CAC  = ad spend ÷ deals / new customers

Sheet columns (header row, any order; missing columns are fine):
  date, source, orders, revenue, leads, qualified_leads, deals, notes
Publish the sheet: File → Share → Publish to web → CSV, and put the link in
accounts.json -> "sales_log": {"csv_url": "..."}   (or {"file": "data/sales/CODE.csv"})
"""
from __future__ import annotations

import calendar
import csv
import io
import urllib.request

from ..util import ROOT, d, div

NUMS = ["orders", "revenue", "leads", "qualified_leads", "deals"]


def load(spec):
    if not spec:
        return []
    try:
        if spec.get("csv_url"):
            with urllib.request.urlopen(spec["csv_url"], timeout=30) as r:
                text = r.read().decode("utf-8-sig")
        else:
            text = (ROOT / spec["file"]).read_text(encoding="utf-8-sig")
    except Exception as e:
        return [{"error": str(e)[:200]}]
    rows = []
    for raw in csv.DictReader(io.StringIO(text)):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not row.get("date"):
            continue
        try:
            row["date"] = str(d(row["date"]))
        except ValueError:
            continue
        for k in NUMS:
            try:
                row[k] = float(str(row.get(k) or 0).replace(",", ""))
            except ValueError:
                row[k] = 0.0
        rows.append(row)
    return rows


def summarize(rows, spend_by_day, as_of, targets):
    """Month-to-date and last-7-days business results against ad spend."""
    if not rows or rows[0].get("error"):
        return {"connected": False, "error": rows[0]["error"] if rows else None}
    as_of = d(as_of)
    first = as_of.replace(day=1)
    lo7 = as_of.toordinal() - 6

    def agg(pred):
        out = {k: sum(r[k] for r in rows if pred(d(r["date"]))) for k in NUMS}
        out["spend"] = sum(v for day, v in spend_by_day.items() if pred(d(day)))
        out["mer"] = div(out["revenue"], out["spend"])
        out["cpql"] = div(out["spend"], out["qualified_leads"])
        out["cac"] = div(out["spend"], out["deals"] or out["orders"])
        out["qual_rate"] = div(out["qualified_leads"], out["leads"])
        out["close_rate"] = div(out["deals"], out["qualified_leads"] or out["leads"])
        return out

    mtd = agg(lambda x: first <= x <= as_of)
    last7 = agg(lambda x: lo7 <= x.toordinal() <= as_of.toordinal())
    by_source = {}
    for r in rows:
        if first <= d(r["date"]) <= as_of:
            s = by_source.setdefault(r.get("source") or "غير محدد", {"orders": 0.0, "revenue": 0.0, "deals": 0.0})
            s["orders"] += r["orders"]
            s["revenue"] += r["revenue"]
            s["deals"] += r["deals"]
    last_entry = max(r["date"] for r in rows)
    res = {"connected": True, "mtd": mtd, "last7": last7, "by_source": by_source, "last_entry": last_entry,
           "stale_days": (as_of - d(last_entry)).days, "targets": targets}
    t = targets or {}
    if t.get("monthly_sales") and mtd["spend"]:
        days_in = as_of.day
        dim = calendar.monthrange(as_of.year, as_of.month)[1]
        res["sales_pace"] = div(mtd["revenue"], t["monthly_sales"] * days_in / dim)
    return res
