#!/usr/bin/env python3
"""
Healthcheck Agent — ping GitHub Actions status for all bots, send daily report to Telegram.
Uses `gh` CLI (already authenticated) to query last run per repo.
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

GITHUB_USER = "lychieuan369-spec"

BOTS = [
    {"name": "BTC",       "repo": "bitcoin-egan-agent"},
    {"name": "ETH",       "repo": "eth-egan-agent"},
    {"name": "Gold",      "repo": "gold-egan-agent"},
    {"name": "VNStock",   "repo": "vnstock-morning-report"},
    {"name": "MacroDaily","repo": "macro-daily-report"},
    {"name": "HSK",       "repo": "hsk-telegram-bot"},
    {"name": "DongY",     "repo": "dong-y-reminder"},
    {"name": "DichCabin", "repo": "dich-cabin-bot"},
]

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8639655584:AAGKmEwGKEufCYwItf3v4c7G_P5acacAwQA")
CHAT_ID   = os.environ.get("CHAT_ID",   "8842938928")


def get_last_run(repo: str) -> dict:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{GITHUB_USER}/{repo}/actions/runs",
             "--jq", ".workflow_runs[0] | {status, conclusion, created_at}"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()[:100]}
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": str(e)[:100]}


def fmt_run(run: dict) -> str:
    if "error" in run:
        return f"⛔ ERROR: {run['error']}"
    conclusion = run.get("conclusion", "unknown")
    status     = run.get("status", "unknown")
    created_at = run.get("created_at", "")[:16].replace("T", " ")
    emoji = {"success": "✅", "failure": "❌", "cancelled": "⚠️"}.get(conclusion, "❓")
    return f"{emoji} {conclusion.upper()} — last run {created_at} UTC"


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        if not body.get("ok"):
            print(f"[ERROR] Telegram: {body}", file=sys.stderr)


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 <b>BOT HEALTHCHECK</b> — {now}", ""]

    all_ok = True
    for bot in BOTS:
        run = get_last_run(bot["repo"])
        status_str = fmt_run(run)
        lines.append(f"<b>{bot['name']}</b>: {status_str}")
        if run.get("conclusion") != "success":
            all_ok = False

    lines.append("")
    lines.append("✅ Tất cả OK" if all_ok else "⚠️ Có bot lỗi — check GitHub Actions")

    message = "\n".join(lines)
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    main()
