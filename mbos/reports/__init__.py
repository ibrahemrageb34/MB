"""Text reports: 10-minute breakdown, CEO layer, Team layer, Roadmap. Markdown so they
render on GitHub, Telegram (subset), Notion and Google Docs."""
from __future__ import annotations

from ..engine.metrics import RESULT_LABEL
from ..util import money, num, pctfmt

STATUS_AR = {"good": "🟢 سليم", "warning": "🟡 تحت المراقبة", "critical": "🔴 محتاج تدخل"}
WALLET_AR = {"ok": "🟢", "warning": "🟡", "critical": "🔴", "debt": "⛔", "unknown": "⚪"}


def _k(r):
    return r["kpi"]["last7"], r["kpi"]["prev7"], r["business"]["target_cpa"], r["currency"]


def breakdown(results, portfolio):
    """The daily 10-minute breakdown: ~60-80 seconds of reading per account."""
    out = [f"# الـ Breakdown اليومي — {results[0]['as_of']}", "",
           f"**الصرف 7 أيام:** {money(portfolio['spend7'])} · **الإيراد المنسوب:** {money(portfolio['revenue7'])} · "
           f"**محتاجين شحن خلال 7 أيام:** {money(portfolio['treasury']['total_need_next_7d'])}", ""]
    if portfolio["p0"]:
        out += ["## 🔴 P0 — قبل أي حاجة", ""]
        out += [f"- **{a['account']}** — {a['title']} → {a['how']} ({a['owner']})" for a in portfolio["p0"]]
        out.append("")
    for r in sorted(results, key=lambda x: x["health"]["score"]):
        k7, p7, target, cur = _k(r)
        label = RESULT_LABEL.get(r["business"]["objective"], "نتيجة")
        w = r["prepaid"]
        out += [f"## {r['name']} — {r['health']['score']}/100 {STATUS_AR[r['health']['status']]}",
                f"- **7 أيام:** صرف {money(k7['spend'], cur)} · {num(k7['results'])} {label} · CPR {money(k7['cpr'], cur)} "
                f"(تارجت {money(target, cur)}) · مقارنة بالأسبوع اللي قبله {pctfmt(_chg(k7['cpr'], p7['cpr']))}"
                + (f" · ROAS {k7['roas']:.2f}" if k7.get("roas") else ""),
                f"- **الرصيد:** {WALLET_AR.get(w.get('status'), '')} {w.get('message', '')}"]
        top = r["actions"][:3]
        if top:
            out.append("- **أهم 3 قرارات:**")
            out += [f"  {i + 1}. [{a['priority']}] {a['title']} — {a['how']}" for i, a in enumerate(top)]
        else:
            out.append("- **مفيش إجراء مطلوب النهارده.** سيب الخوارزمية تشتغل.")
        promos = [p for p in r["posts"] if p["verdict"] == "promote"]
        if promos:
            out.append(f"- **بوست جديد يستحق إعلان:** {promos[0]['caption'][:60]}… (Score {promos[0]['score']})")
        out.append("")
    return "\n".join(out)


def ceo(results, portfolio):
    crit = [h for h in portfolio["health"] if h["status"] == "critical"]
    out = [f"# CEO Layer — {results[0]['as_of']}", "", "## الملخص", "",
           f"- **{len(results)} أكونتات** · صرف 7 أيام {money(portfolio['spend7'])} · إيراد منسوب {money(portfolio['revenue7'])}",
           f"- **{len(crit)} أكونت محتاج تدخل**" + (f": {', '.join(h['name'] for h in crit)}" if crit else ""),
           f"- **سيولة الشحن المطلوبة خلال 7 أيام:** {money(portfolio['treasury']['total_need_next_7d'])}", "",
           "## الأكونتات", "", "| الأكونت | الصحة | CPR 7 أيام | مقابل التارجت | الرصيد (أيام) | التوقع لنهاية الشهر |",
           "|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: x["health"]["score"]):
        k7, _, target, cur = _k(r)
        w = r["prepaid"]
        rd = f"{w['runway_days']:.1f}" if w.get("runway_days") is not None else "—"
        out.append(f"| {r['name']} | {r['health']['score']} {STATUS_AR[r['health']['status']].split()[0]} | {money(k7['cpr'], cur)} | "
                   f"{(r['health']['cpr_ratio'] or 0):.2f}× | {WALLET_AR.get(w.get('status'), '')} {rd} | "
                   f"{money(r['forecast']['month_end_spend'], cur)} صرف / {num(r['forecast']['month_end_results'])} نتيجة |")
    if portfolio.get("brands"):
        out += ["", "## البراندات — النتيجة الحقيقية (شيت المبيعات)", "",
                "| البراند | صرف الشهر | مبيعات الشهر | MER | التارجت | تكلفة الليد المؤهل |", "|---|---|---|---|---|---|"]
        for b in portfolio["brands"]:
            s, t = b["sales"], b["targets"] or {}
            if not s.get("connected"):
                out.append(f"| {b['brand']} | — | ⚠️ شيت المبيعات مش متوصّل | — | {t.get('target_mer', '—')} | — |")
                continue
            m = s["mtd"]
            out.append(f"| {b['brand']} | {money(m['spend'])} | {money(m['revenue'])} | "
                       f"{(m['mer'] or 0):.1f}× | {t.get('target_mer', '—')}× | {money(m['cpql'])} |")
    out += ["", "## قرارات مطلوبة من الإدارة", ""]
    decisions = []
    for t in portfolio["treasury"]["rows"]:
        if t["status"] in ("debt", "critical", "warning"):
            decisions.append(f"- اعتماد شحن **{money(t['need_next_7d'])}** لـ {t['account']} قبل {t['topup_by']}")
    for r in results:
        for b in r["budget"]:
            if b["action"] == "scale":
                decisions.append(f"- موافقة على زيادة ميزانية {r['name']} ({b['name']}) من {b['current']:,.0f} لـ {b['recommended']:,.0f}/يوم — {b['why']}")
    out += decisions or ["- مفيش قرارات معلّقة."]
    out += ["", "## المخاطر", ""]
    risks = []
    for r in results:
        for a in r["actions"]:
            if a["area"] == "anomaly":
                risks.append(f"- **{r['name']}:** {a['title']} — {a['how']}")
        if r["forecast"].get("vs_budget") and r["forecast"]["vs_budget"] > 1.1:
            risks.append(f"- **{r['name']}:** متوقع يعدّي الميزانية الشهرية بـ {(r['forecast']['vs_budget'] - 1) * 100:.0f}%")
    out += risks or ["- مفيش مخاطر حرجة."]
    out += ["", "## الأولويات (أعلى 5 على مستوى الشركة)", ""]
    allacts = sorted([a for r in results for a in r["actions"]], key=lambda a: ({"P0": 0, "P1": 1, "P2": 2, "P3": 3}[a["priority"]], -a["ice"]))
    out += [f"{i + 1}. [{a['priority']}] **{a['account']}** — {a['title']}" for i, a in enumerate(allacts[:5])]
    return "\n".join(out)


def team(results):
    out = [f"# Team Layer — خطة التنفيذ ({results[0]['as_of']})", "",
           "| الأولوية | الأكونت | المهمة | إزاي | المسؤول | الأداة | الموعد | KPI | ICE |",
           "|---|---|---|---|---|---|---|---|---|"]
    allacts = sorted([a for r in results for a in r["actions"]], key=lambda a: ({"P0": 0, "P1": 1, "P2": 2, "P3": 3}[a["priority"]], -a["ice"]))
    for a in allacts:
        out.append(f"| {a['priority']} | {a['account']} | {a['title']} | {a['how'].replace('|', '/')} | {a['owner']} | "
                   f"{a['tool']} | {a['due']} | {a['kpi']} | {a['ice']} |")
    out += ["", "## ملخص الفريق الإبداعي", ""]
    for r in results:
        notes = r["creative_insights"]["notes"]
        if notes or r["ideas"]:
            out.append(f"### {r['name']}")
            out += [f"- {n['text']}" for n in notes[:4]]
            out += [f"- **فكرة اختبار:** {i['title']} — {i['hypothesis']}" for i in r["ideas"][:3]]
            out.append("")
    return "\n".join(out)


def roadmap_md(results):
    out = ["# Roadmap & Journal", ""]
    for r in results:
        rm = r["roadmap"]
        out += [f"## {r['name']}", f"- **المرحلة الحالية:** {rm['current_phase'] or '—'} · **الإنجاز:** {rm['overall'] * 100:.0f}%",
                "- **اللي نجح:** " + ("؛ ".join(e["title"] for e in rm["wins"]) or "—"),
                "- **اللي أثّر بالسلب:** " + ("؛ ".join(e["title"] for e in rm["hurts"]) or "—"),
                "- **فاضل:** " + ("؛ ".join(rm["remaining"][:6]) or "—"), "", r["roadmap_mermaid"], ""]
    return "\n".join(out)


def _chg(a, b):
    if a is None or not b:
        return None
    return (a - b) / b
