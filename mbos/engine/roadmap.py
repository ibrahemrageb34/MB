"""Account journal + roadmap: the record of what happened, where we are, and what is left.

data/journal/<account_key>.json
{
  "phases": [{"name": "...", "status": "done|active|todo", "start": "...", "end": "...",
              "tasks": [{"title": "...", "done": true}]}],
  "events": [{"date": "...", "type": "launch|decision|test|result|issue|milestone",
              "title": "...", "impact": "positive|negative|neutral", "detail": "...", "auto": false}]
}
The engine appends auto events (test winners, prepaid debt, tracking breaks...) with de-duplication,
so the history builds itself while the team keeps adding the decisions.
"""
from __future__ import annotations

from ..util import load_json, save_json

DEFAULT_PHASES = [
    {"name": "Onboarding & Business Truth", "tasks": ["اقتصاديات المنتج (AOV/Margin/CAC)", "الأهداف والـ KPIs", "صلاحيات الأكونتات"]},
    {"name": "Tracking Foundation", "tasks": ["Pixel + CAPI", "Event Match Quality ≥ 7", "UTMs + GA4", "Naming convention"]},
    {"name": "Account Structure", "tasks": ["كامبين Scaling", "كامبين Testing", "Retargeting (لو الحجم يسمح)"]},
    {"name": "Creative Testing Engine", "tasks": ["Angle bank", "3 اختبارات/أسبوع", "Testing board"]},
    {"name": "Scaling", "tasks": ["قواعد السكيل", "Prepaid runway ≥ 7 أيام", "Creative refresh cadence"]},
    {"name": "Expansion", "tasks": ["TikTok", "Snapchat", "Google"]},
]


def load(path):
    j = load_json(path, None)
    if j is None:
        j = {"phases": [{"name": p["name"], "status": "todo", "tasks": [{"title": t, "done": False} for t in p["tasks"]]}
                        for p in DEFAULT_PHASES], "events": []}
    return j


def auto_events(as_of, anomalies, prepaid, tests, qa):
    ev = []
    for a in anomalies:
        if a["severity"] == "critical":
            ev.append({"date": as_of, "type": "issue", "impact": "negative", "auto": True,
                       "title": f"{a['metric_ar']} — {a['entity']}", "detail": a["hint"]})
    if prepaid.get("status") in ("debt", "critical"):
        ev.append({"date": as_of, "type": "issue", "impact": "negative", "auto": True,
                   "title": "رصيد مسبق الدفع" + (" — مديونية" if prepaid["status"] == "debt" else " — أقل من يومين"),
                   "detail": prepaid["message"]})
    for t in tests:
        if t["status"] in ("winner", "loser") and not t.get("logged"):
            ev.append({"date": as_of, "type": "result", "impact": "positive" if t["status"] == "winner" else "neutral",
                       "auto": True, "title": f"اختبار {t['id']}: {'كسب' if t['status'] == 'winner' else 'خسر'}",
                       "detail": t.get("hypothesis", "")})
    for i in qa:
        if i["priority"] == "P0":
            ev.append({"date": as_of, "type": "issue", "impact": "negative", "auto": True,
                       "title": i["title"], "detail": i["entity"]})
    return ev


def merge(journal, new_events):
    keys = {(e["date"], e["title"]) for e in journal["events"]}
    for e in new_events:
        if (e["date"], e["title"]) not in keys:
            journal["events"].append(e)
            keys.add((e["date"], e["title"]))
    journal["events"].sort(key=lambda e: e["date"])
    return journal


def progress(journal):
    phases = []
    for p in journal["phases"]:
        tasks = p.get("tasks", [])
        done = sum(1 for t in tasks if t.get("done"))
        phases.append({**p, "done": done, "total": len(tasks), "pct": done / len(tasks) if tasks else 0})
    all_t = sum(p["total"] for p in phases) or 1
    current = next((p["name"] for p in phases if p.get("status") == "active"), None)
    wins = [e for e in journal["events"] if e.get("impact") == "positive"]
    hurts = [e for e in journal["events"] if e.get("impact") == "negative"]
    remaining = [f"{p['name']}: {t['title']}" for p in phases for t in p.get("tasks", []) if not t.get("done")]
    return {"phases": phases, "overall": sum(p["done"] for p in phases) / all_t, "current_phase": current,
            "wins": wins[-8:], "hurts": hurts[-8:], "remaining": remaining[:10], "events": journal["events"][-30:]}


def mermaid(name, journal):
    """Mermaid gantt of the phases + timeline of the events (renders on GitHub)."""
    lines = ["```mermaid", "gantt", f"    title {name} — Roadmap", "    dateFormat YYYY-MM-DD"]
    for p in journal["phases"]:
        tag = {"done": "done, ", "active": "active, "}.get(p.get("status"), "")
        if p.get("start"):
            end = p.get("end") or p["start"]
            lines.append(f"    {p['name']} :{tag}{p['start']}, {end}")
    lines.append("```")
    lines += ["", "```mermaid", "timeline", f"    title {name} — ما حدث"]
    for e in journal["events"][-20:]:
        mark = {"positive": "✅", "negative": "⚠️"}.get(e.get("impact"), "•")
        lines.append(f"    {e['date']} : {mark} {e['title'].replace(':', ' -')}")
    lines.append("```")
    return "\n".join(lines)


def save(path, journal):
    save_json(path, journal)
