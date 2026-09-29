"""Builds the single-file dashboard (data embedded as JSON; no server needed)."""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")


def build(results, portfolio, demo=False, bare=False):
    data = json.dumps({"demo": demo, "portfolio": portfolio, "accounts": results},
                      ensure_ascii=False, default=str).replace("</", "<\\/")
    body = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", data)
    if bare:  # for hosts that supply their own <html>/<head> skeleton
        return body
    return ('<!doctype html>\n<html lang="ar" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>body{margin:0}[hidden]{display:none!important}</style></head><body>\n'
            + body + "\n</body></html>\n")
