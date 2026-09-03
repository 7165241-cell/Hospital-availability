"""
בודק אם תוכן הגיליון השתנה מאז הבדיקה הקודמת:
  • השתנה  → שולח מיד לוח מעודכן לערוץ (עם כותרת "עדכון בלוח").
  • לא השתנה, אבל עבר יותר מ-20 שעות מהפוסט האחרון וכבר בוקר → שולח "עדכון יומי".
המצב נשמר ב-state/board_state.json ומתעדכן ב-repo אחרי כל שליחה.

הסקריפט לעולם לא מפיל את הריצה (exit 0) — כל תקלה נרשמת בסיכום הריצה ב-GitHub.
"""

from __future__ import annotations

import json
import os
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import board

STATE = Path("state/board_state.json")
TG = "https://api.telegram.org/bot{token}/{method}"

MORNING_HOUR = int(os.environ.get("DAILY_HOUR", "8"))
STALE_HOURS = 20


def tg(method: str, **params) -> dict:
    token = os.environ["BOT_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    url = TG.format(token=token, method=method)
    try:
        with urllib.request.urlopen(url, data=data, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except ValueError:
            return {"ok": False, "error_code": err.code, "description": body}
    except urllib.error.URLError as err:
        return {"ok": False, "error_code": 0, "description": f"network: {err.reason}"}


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def run() -> None:
    if not os.environ.get("BOT_TOKEN"):
        board.note("❌ חסר Secret בשם BOT_TOKEN ב-repo.")
        return
    if not os.environ.get("CHANNEL_ID"):
        board.note(
            "❌ חסר Secret בשם CHANNEL_ID ב-repo. "
            "Settings ➜ Secrets and variables ➜ Actions ➜ New repository secret, "
            "בשם CHANNEL_ID ובערך -1004297375221"
        )
        return

    tz = ZoneInfo(os.environ.get("TZ", "Asia/Jerusalem"))
    now = datetime.now(tz)

    raw = board.fetch_csv_sync()
    current = board.render_board(raw).strip()

    state = load_state()
    prev = (state.get("board") or "").strip()
    changed = bool(current) and current != prev

    last_post = state.get("last_post")
    if last_post:
        try:
            hrs = (now - datetime.fromisoformat(last_post)).total_seconds() / 3600
            stale = hrs >= STALE_HOURS and now.hour >= MORNING_HOUR
        except ValueError:
            stale = True
    else:
        stale = True

    if not changed and not stale:
        print(f"אין שינוי ({now:%Y-%m-%d %H:%M})")
        return

    channel = os.environ["CHANNEL_ID"]
    prefix = "🔔 <b>עדכון בלוח הזמינות</b>\n\n" if (changed and prev) else ""
    text = prefix + board.build_board_text(raw, now)

    res = tg(
        "sendMessage",
        chat_id=channel,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview="true",
    )
    if not res.get("ok"):
        desc = res.get("description", "")
        hint = ""
        if "chat not found" in str(desc):
            hint = (
                "\nהבוט לא מוצא את הערוץ — צריך להוסיף את @hospital_availability_bot "
                "כמנהל בערוץ, או שה-CHANNEL_ID שגוי."
            )
        elif "not enough rights" in str(desc) or "CHAT_ADMIN_REQUIRED" in str(desc):
            hint = "\nלבוט אין הרשאת 'פרסום הודעות' בערוץ."
        board.note(f"❌ שליחת ההודעה נכשלה: {json.dumps(res, ensure_ascii=False)}{hint}")
        return

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(
            {"board": current, "last_post": now.isoformat(timespec="seconds")},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print("נשלח:", "שינוי" if changed else "עדכון יומי", f"({now:%Y-%m-%d %H:%M})")


def main() -> int:
    try:
        run()
    except Exception:  # noqa: BLE001
        board.note("❌ שגיאה ב-watch_sheet:\n```\n" + traceback.format_exc() + "\n```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
