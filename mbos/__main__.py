"""CLI.

  python -m mbos run --demo              # full daily run on demo data
  python -m mbos run                     # full run on config/accounts.json via Meta API
  python -m mbos alerts --kind prepaid   # hourly wallet check (for cron/n8n)
  python -m mbos alerts --kind posts     # new-post watcher (every 30-60 min)
  python -m mbos apply-spend-caps --yes  # write the recommended spending limits to Meta
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import notify, pipeline, reports
from .dashboard import build as build_dashboard
from .util import ROOT, load_json, save_json


def load_env():
    """KEY=VALUE lines from .env (server secrets); real environment variables win."""
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_cfg():
    cfg = load_json(ROOT / "config/settings.json")
    local = load_json(ROOT / "config/settings.local.json", {})
    for k, v in local.items():
        cfg[k] = {**cfg.get(k, {}), **v} if isinstance(v, dict) else v
    return cfg


def load_accounts(demo):
    path = ROOT / "config/accounts.json"
    if demo or not path.exists():
        if not demo:
            sys.exit("config/accounts.json not found — copy config/accounts.example.json, or use --demo")
        path = ROOT / "config/accounts.example.json"
    return load_json(path)


def collect(args, cfg):
    # Alerts run every 30-60 min: pull 14 days instead of 35 to stay far from API rate limits.
    days = 35 if args.cmd == "run" else 14
    accounts = load_accounts(args.demo)
    bundles = []
    if args.demo:
        from .connectors import demo
        bundles = [demo.build(a, i) for i, a in enumerate(accounts)]
    else:
        from .connectors.meta import MetaAPI
        apis = {}
        for a in accounts:
            if a.get("platform", "meta") != "meta":
                continue
            try:
                env = a.get("token_env") or cfg["meta"]["access_token_env"]  # one token per Business Manager
                apis.setdefault(env, MetaAPI(cfg, env))
                bundles.append(apis[env].fetch(a, days=days))
            except Exception as e:  # one broken account must not block the other six
                print(f"[{a['name']}] fetch failed: {e}", file=sys.stderr)
    results = [r for b in bundles for r in pipeline.analyze_bundle(b, cfg, persist=not args.demo)]
    return results, pipeline.portfolio(results, cfg)


def _dedupe(out: Path, key: str, items: list):
    """Send each alert once per key, so hourly checks don't repeat themselves."""
    state_p = out / "state.json"
    state = load_json(state_p, {})
    seen = state.get(key, [])
    fresh = [(k, text) for k, text in items if k not in seen]
    state[key] = (seen + [k for k, _ in fresh])[-2000:]
    save_json(state_p, state)
    return "\n\n".join(text for _, text in fresh)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mbos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "alerts", "apply-spend-caps"):
        p = sub.add_parser(name)
        p.add_argument("--demo", action="store_true")
        p.add_argument("--out", default=str(ROOT / "output"))
        p.add_argument("--no-notify", action="store_true")
        if name == "alerts":
            p.add_argument("--kind", choices=["all", "prepaid", "anomaly", "posts"], default="all")
        if name == "apply-spend-caps":
            p.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)
    load_env()
    cfg = load_cfg()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results, port = collect(args, cfg)
    if not results:
        sys.exit("No account data collected.")

    if args.cmd == "run":
        (out / "breakdown.md").write_text(reports.breakdown(results, port), encoding="utf-8")
        (out / "ceo.md").write_text(reports.ceo(results, port), encoding="utf-8")
        (out / "team.md").write_text(reports.team(results), encoding="utf-8")
        (out / "roadmap.md").write_text(reports.roadmap_md(results), encoding="utf-8")
        save_json(out / "results.json", {"portfolio": port, "accounts": results})
        (out / "dashboard.html").write_text(build_dashboard(results, port, demo=args.demo), encoding="utf-8")
        print(f"Wrote {out}/dashboard.html, breakdown.md, ceo.md, team.md, roadmap.md, results.json")
        if not args.no_notify:
            notify.telegram(cfg, reports.breakdown(results, port))
            notify.webhook(cfg, {"type": "daily", "portfolio": port,
                                 "accounts": [{k: r[k] for k in ("name", "health", "actions", "prepaid")} for r in results]})

    elif args.cmd == "alerts":
        text = _dedupe(out, args.kind, notify.alert_items(results, port, args.kind))
        print(text or "no new alerts")
        if text and not args.no_notify:
            notify.telegram(cfg, text)
            notify.webhook(cfg, {"type": f"alert_{args.kind}", "text": text})

    elif args.cmd == "apply-spend-caps":
        plan = [(r["name"], r["key"], r["prepaid"].get("spend_cap_recommended")) for r in results if r["primary"]]
        print(json.dumps(plan, ensure_ascii=False, indent=1))
        if args.demo or not args.yes:
            print("Dry run. Re-run without --demo and with --yes to write spending limits to Meta.")
            return
        from .connectors.meta import MetaAPI
        accounts = {a.get("code"): a for a in load_accounts(False)}
        for name, key, cap in plan:
            a = accounts.get(key)
            if cap and a:
                api = MetaAPI(cfg, a.get("token_env"))
                act = a["id"] if a["id"].startswith("act_") else f"act_{a['id']}"
                print(name, api.set_spend_cap(act, cap))


if __name__ == "__main__":
    main()
