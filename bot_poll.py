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


def wants_update(msg: dict) -> bool:
    text = (msg.get("text") or "").strip().lower().lstrip("/")
    if not text:
        return False
    if msg.get("chat", {}).get("type") == "private":
        return True  # בצ'אט פרטי כל הודעה נחשבת בקשת עדכון
    return any(word in text for word in TRIGGERS)


def main() -> int:
    now = datetime.now(ZoneInfo(os.environ.get("TZ", "Asia/Jerusalem")))
    res = tg("getUpdates", timeout=0, allowed_updates=json.dumps(["message"]))
    if not res.get("ok"):
        print("getUpdates error:", json.dumps(res, ensure_ascii=False))
        return 1

    updates = res["result"]
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


if __name__ == "__main__":
    raise SystemExit(main())
