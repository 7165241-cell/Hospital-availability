"""
שליחת לוח הזמינות היומי לערוץ טלגרם — רץ ב-GitHub Actions לפי שעון.
ספרייה סטנדרטית בלבד, בלי pip install.

משתני סביבה:
  BOT_TOKEN   — חובה. הטוקן מ-@BotFather
  CHANNEL_ID  — חובה. @שם_הערוץ או מזהה מספרי (למשל -1001234567890)
  DAILY_HOUR  — ברירת מחדל 8. הסקריפט שולח רק אם השעה המקומית (ישראל) שווה לזה,
                אלא אם מריצים עם FORCE=1 / --force. כך זה תמיד 08:xx שעון ישראל
                גם כשיש/אין שעון קיץ, למרות ש-cron של GitHub הוא ב-UTC.
  TZ          — ברירת מחדל Asia/Jerusalem
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import board

TG_API = "https://api.telegram.org/bot{token}/{method}"


def tg(method: str, **params) -> dict:
    token = os.environ["BOT_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    url = TG_API.format(token=token, method=method)
    try:
        with urllib.request.urlopen(url, data=data, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:  # Telegram מחזיר גוף JSON גם בשגיאות 4xx
        body = err.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except ValueError:
            return {"ok": False, "error_code": err.code, "description": body}


def main() -> int:
    force = "--force" in sys.argv or os.environ.get("FORCE") == "1"
    tz = ZoneInfo(os.environ.get("TZ", "Asia/Jerusalem"))
    daily_hour = int(os.environ.get("DAILY_HOUR", "8"))
    now = datetime.now(tz)

    if not force and now.hour != daily_hour:
        print(f"skip: local time {now:%Y-%m-%d %H:%M} (hour {now.hour} != {daily_hour})")
        return 0

    channel = os.environ["CHANNEL_ID"]
    raw = board.fetch_csv_sync()
    text = board.build_board_text(raw, now)

    res = tg(
        "sendMessage",
        chat_id=channel,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview="true",
    )
    if not res.get("ok"):
        print("Telegram error:", json.dumps(res, ensure_ascii=False))
        return 1
    print(f"posted to {channel} at {now:%Y-%m-%d %H:%M %Z}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
