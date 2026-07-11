#!/usr/bin/env python3
"""
Railway Usage Alert — query current-month workspace usage via GraphQL,
alert Telegram when spend crosses THRESHOLD_USD. Also tracks whether the
alert already fired this month (via a small state file committed back to
the repo) so it doesn't spam every run.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
RAILWAY_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")
WORKSPACE_ID = os.environ.get("RAILWAY_WORKSPACE_ID", "cd20c6ac-2652-43ce-8c95-a6e66c73b89c")

THRESHOLD_USD = float(os.environ.get("THRESHOLD_USD", "5"))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8639655584:AAGKmEwGKEufCYwItf3v4c7G_P5acacAwQA")
CHAT_ID = os.environ.get("CHAT_ID", "8842938928")

STATE_FILE = "railway_usage_state.json"

USAGE_QUERY = """
query WorkspaceUsage($workspaceId: String!) {
  workspace(workspaceId: $workspaceId) {
    customer {
      currentUsage
    }
  }
}
"""

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"


def graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        RAILWAY_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RAILWAY_TOKEN}",
            "User-Agent": UA,  # Cloudflare chặn user-agent mặc định của urllib
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        if "errors" in body:
            raise RuntimeError(str(body["errors"])[:300])
        return body["data"]


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


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def main():
    if not RAILWAY_TOKEN:
        print("[ERROR] RAILWAY_API_TOKEN chưa được set — bỏ qua check.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")

    try:
        data = graphql(USAGE_QUERY, {"workspaceId": WORKSPACE_ID})
        cost = float(data["workspace"]["customer"]["currentUsage"])
    except Exception as e:
        print(f"[ERROR] Không lấy được usage: {e}", file=sys.stderr)
        # Báo lỗi qua Telegram để biết script hỏng, không âm thầm im lặng
        send_telegram(f"⚠️ <b>Railway Usage Alert lỗi</b>\nKhông query được usage: {str(e)[:200]}")
        sys.exit(1)

    state = load_state()
    already_alerted = state.get(month_key, {}).get("alerted", False)

    print(f"[{now.isoformat()}] Railway usage tháng {month_key}: ${cost:.2f} (ngưỡng ${THRESHOLD_USD})")

    if cost >= THRESHOLD_USD and not already_alerted:
        send_telegram(
            f"🚨 <b>RAILWAY VƯỢT NGƯỠNG ${THRESHOLD_USD:.0f}</b>\n\n"
            f"Chi phí tháng {month_key}: <b>${cost:.2f}</b>\n"
            f"Check dashboard: https://railway.com/account/usage"
        )
        state[month_key] = {"alerted": True, "cost_at_alert": cost}
        save_state(state)
    elif cost >= THRESHOLD_USD and already_alerted:
        print("Đã báo rồi tháng này, không spam lại.")
    else:
        # reset flag nếu sang tháng mới / chưa vượt ngưỡng
        state.setdefault(month_key, {})["alerted"] = False
        state[month_key]["cost_at_alert"] = cost
        save_state(state)


if __name__ == "__main__":
    main()
