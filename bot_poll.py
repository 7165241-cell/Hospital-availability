"""
מענה ל"עדכון עכשיו" — רץ ב-GitHub Actions כל כמה דקות.

מי ששולח הודעה לבוט @hospital_availability_bot (צ'אט פרטי — כל הודעה),
או כותב "עדכון" בקבוצת דיון מקושרת לערוץ — מקבל את הלוח העדכני של אותו רגע.

אין מצב מקומי: Telegram עצמו זוכר אילו עדכונים כבר טופלו (מנגנון offset),
כך שכל ריצה מטפלת רק בהודעות חדשות.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import board

TG = "https://api.telegram.org/bot{token}/{method}"

TRIGGERS = ("עדכון", "עדכן", "מצב", "update", "status", "start")


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


def wants_update(msg: dict) -> bool:
    text = (msg.get("text") or "").strip().lower().lstrip("/")
    if not text:
        return False
    if msg.get("chat", {}).get("type") == "private":
        return True  # בצ'אט פרטי כל הודעה נחשבת בקשת עדכון
    return any(word in text for word in TRIGGERS)


def main() -> int:
    now = datetime.now(ZoneInfo(os.environ.get("TZ", "Asia/Jerusalem")))
    tg("deleteWebhook")  # ליתר ביטחון — הבוט עובד ב-polling, לא webhook
    res = tg("getUpdates", timeout=0, allowed_updates=json.dumps(["message"]))
    if not res.get("ok"):
        code = res.get("error_code")
        msg = json.dumps(res, ensure_ascii=False)
        if code == 409:
            # מופע אחר של הבוט מושך עדכונים (למשל bot.py מקומי) — לא שגיאה אמיתית
            print("getUpdates conflict — another bot instance is polling. skipping.")
            return 0
        if code in (401, 404):
            board.note("❌ בעיית טוקן (BOT_TOKEN): " + msg)
            return 0
        print("getUpdates transient error (ignored):", msg)
        return 0

    updates = res.get("result") or []
    if not updates:
        print("no pending updates")
        return 0

    board_text: str | None = None
    sent = 0
    for upd in updates:
        msg = upd.get("message")
        if not msg or not wants_update(msg):
            continue
        if board_text is None:
            board_text = board.build_board_text(board.fetch_csv_sync(), now)
        r = tg(
            "sendMessage",
            chat_id=msg["chat"]["id"],
            text=board_text,
            parse_mode="HTML",
            disable_web_page_preview="true",
            reply_to_message_id=msg["message_id"],
        )
        if r.get("ok"):
            sent += 1
        else:
            print("sendMessage error:", json.dumps(r, ensure_ascii=False))

    # מסמן את כל העדכונים כטופלו כך שלא יחזרו בריצה הבאה
    tg("getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)
    print(f"processed {len(updates)} updates, sent {sent} replies")
    return 0


def _safe_main() -> int:
    try:
        return main()
    except Exception:  # noqa: BLE001
        import traceback

        board.note("⚠️ שגיאה ב-bot_poll:\n```\n" + traceback.format_exc() + "\n```")
        return 0


if __name__ == "__main__":
    raise SystemExit(_safe_main())
