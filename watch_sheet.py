"""
שולח את לוח הזמינות לערוץ במקרים הבאים:
  • תוכן הגיליון השתנה מאז הבדיקה הקודמת  → שליחה מיידית ("🔔 עדכון בלוח").
  • הגיע אחד ממועדי השליחה הקבועים (POST_TIMES, ברירת מחדל 07:30 / 15:30 / 23:30
    שעון ישראל) ועוד לא נשלח באותו מועד היום → שליחת הלוח הנוכחי.

הריצה כל 5 דקות, אז השליחה במועד קבוע מגיעה תוך ~5–15 דקות מהשעה.
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

# מועדי שליחה קבועים לערוץ (שעון ישראל). ניתן לשנות דרך Secret/משתנה POST_TIMES.
POST_TIMES = os.environ.get("POST_TIMES", "07:30,15:30,23:30")
# חלון בשעות שבו עדיין שולחים מועד שעבר (אם GitHub עיכב ריצות). המועדים 8 שעות זה מזה.
SLOT_WINDOW_HOURS = 6


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


def parse_slots(text: str) -> list[tuple[int, int]]:
    slots = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        hh, mm = part.split(":")
        slots.append((int(hh), int(mm)))
    return sorted(slots)


def due_slot(now: datetime) -> tuple[str, float] | None:
    """המועד הקבוע האחרון שעבר היום: (מזהה, כמה שעות עברו). None אם אף מועד לא עבר."""
    passed = []
    for hh, mm in parse_slots(POST_TIMES):
        slot_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if slot_dt <= now:
            passed.append(slot_dt)
    if not passed:
        return None
    slot_dt = max(passed)
    key = f"{slot_dt:%Y-%m-%d}:{slot_dt:%H%M}"
    hours_ago = (now - slot_dt).total_seconds() / 3600
    return key, hours_ago


def run() -> None:
    if not os.environ.get("BOT_TOKEN"):
        board.note("❌ חסר Secret בשם BOT_TOKEN ב-repo.")
        return
    if not os.environ.get("CHANNEL_ID"):
        board.note(
            "❌ חסר Secret בשם CHANNEL_ID ב-repo. "
            "Settings ➜ Secrets and variables ➜ Actions ➜ New repository secret "
            "(השם: CHANNEL_ID, הערך: מזהה הערוץ המספרי)."
        )
        return

    tz = ZoneInfo(os.environ.get("TZ", "Asia/Jerusalem"))
    now = datetime.now(tz)

    try:
        raw = board.fetch_csv_sync()
    except Exception as err:  # noqa: BLE001
        board.note(f"❌ קריאת הגיליון נכשלה: {err}")
        return
    current = board.render_board(raw).strip()
    board.note(f"קריאת הגיליון: {len(raw)} תווים ({now:%d/%m %H:%M})")

    state = load_state()
    prev = (state.get("board") or "").strip()
    changed = bool(current) and current != prev

    slot = due_slot(now)
    slot_key = slot[0] if slot else state.get("last_slot", "")
    scheduled = bool(slot) and slot[1] <= SLOT_WINDOW_HOURS and state.get("last_slot") != slot[0]

    if not changed and not scheduled:
        board.note(f"אין שינוי, ואין מועד שליחה פתוח ({now:%d/%m %H:%M})")
        # עדיין נעדכן את last_slot כדי לא לשלוח מועד ישן מאוחר יותר
        if slot and state.get("last_slot") != slot[0] and slot[1] > SLOT_WINDOW_HOURS:
            state["last_slot"] = slot[0]
            _save(state.get("board", current), state.get("last_post", ""), slot[0])
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
        desc = str(res.get("description", ""))
        hint = ""
        if "chat not found" in desc:
            hint = (
                "\nהבוט לא מוצא את הערוץ — צריך להוסיף את @hospital_availability_bot "
                "כמנהל בערוץ, או שה-CHANNEL_ID שגוי."
            )
        elif "not enough rights" in desc or "CHAT_ADMIN_REQUIRED" in desc:
            hint = "\nלבוט אין הרשאת 'פרסום הודעות' בערוץ."
        board.note(f"❌ שליחת ההודעה נכשלה: {json.dumps(res, ensure_ascii=False)}{hint}")
        return

    _save(current, now.isoformat(timespec="seconds"), slot_key)
    board.note(
        ("🔔 נשלח לערוץ: עדכון בלוח" if (changed and prev) else "✅ נשלח לערוץ")
        + f" ({now:%d/%m %H:%M})"
    )


def _save(board_text: str, last_post: str, last_slot: str) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(
            {"board": board_text, "last_post": last_post, "last_slot": last_slot},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def main() -> int:
    try:
        run()
    except Exception:  # noqa: BLE001
        board.note("❌ שגיאה ב-watch_sheet:\n```\n" + traceback.format_exc() + "\n```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
