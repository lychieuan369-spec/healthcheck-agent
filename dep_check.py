#!/usr/bin/env python3
"""
Dependency drift checker — checks requirements.txt per repo via GitHub API,
installs them in a venv, runs pip list --outdated, reports to Telegram.
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import base64

GITHUB_USER = "lychieuan369-spec"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8639655584:AAGKmEwGKEufCYwItf3v4c7G_P5acacAwQA")
CHAT_ID   = os.environ.get("CHAT_ID",   "8842938928")

REPOS = [
    "bitcoin-egan-agent",
    "eth-egan-agent",
    "gold-egan-agent",
    "vnstock-morning-report",
    "macro-daily-report",
    "hsk-telegram-bot",
    "dong-y-reminder",
    "dich-cabin-bot",
]


def get_requirements(repo: str) -> str | None:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{GITHUB_USER}/{repo}/contents/requirements.txt",
             "--jq", ".content"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        content = result.stdout.strip()
        return base64.b64decode(content).decode("utf-8")
    except Exception:
        return None


def check_outdated(requirements_txt: str) -> list[dict]:
    # Use a fresh, isolated venv per repo so packages from one repo's
    # requirements.txt never leak into (or get reported for) another repo.
    with tempfile.TemporaryDirectory() as tmpdir:
        req_file = os.path.join(tmpdir, "requirements.txt")
        with open(req_file, "w", encoding="utf-8") as f:
            f.write(requirements_txt.lstrip("﻿"))

        venv_dir = os.path.join(tmpdir, "venv")
        venv_result = subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            capture_output=True, timeout=60
        )
        if venv_result.returncode != 0:
            return []

        venv_python = (
            os.path.join(venv_dir, "Scripts", "python.exe")
            if os.name == "nt"
            else os.path.join(venv_dir, "bin", "python")
        )

        # Install this repo's packages into the isolated venv only
        install_result = subprocess.run(
            [venv_python, "-m", "pip", "install", "-r", req_file, "-q",
             "--disable-pip-version-check"],
            capture_output=True, timeout=120
        )
        if install_result.returncode != 0:
            return []

        # Check outdated within that same isolated venv
        result = subprocess.run(
            [venv_python, "-m", "pip", "list", "--outdated", "--format=json",
             "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return []
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []


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
    lines = ["📦 <b>DEPENDENCY DRIFT REPORT</b>", ""]
    any_outdated = False

    for repo in REPOS:
        reqs = get_requirements(repo)
        if reqs is None:
            lines.append(f"<b>{repo}</b>: ⚠️ no requirements.txt")
            continue

        outdated = check_outdated(reqs)
        if not outdated:
            lines.append(f"<b>{repo}</b>: ✅ all up to date")
        else:
            any_outdated = True
            pkg_list = ", ".join(
                f"{p['name']} {p['version']}→{p['latest_version']}" for p in outdated
            )
            lines.append(f"<b>{repo}</b>: ❗ {pkg_list}")

    lines.append("")
    lines.append("✅ Không có drift" if not any_outdated else "⚠️ Có package cũ — cân nhắc update")

    message = "\n".join(lines)
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    main()
