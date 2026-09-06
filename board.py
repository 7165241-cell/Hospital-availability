"""
לוגיקת קריאה ועיצוב של לוח הזמינות — ספרייה סטנדרטית בלבד (בלי תלויות).
משמש גם את bot.py (הבוט האינטראקטיבי) וגם את daily_post.py (GitHub Actions).
"""

from __future__ import annotations

import csv
import html
import io
import os
import re
import time
import urllib.request
from datetime import datetime

DEFAULT_SHEET_ID = "1ybPhMiIba43GawAzHNl9AJiMCBi61t4NWhQuXCYVwag"

# כותרות הסעיפים בגיליון (קבועות) → (אימוג'י, סוג עיצוב).
#   kv   = שורות "מוסד | סטטוס"
#   duty = שורות "טווח שעות | שם התורן"
#   list = רשימת שורות חופשית
SECTION_META: dict[str, tuple[str, str]] = {
    "זמינות מצנתר מוח": ("🧠", "kv"),
    "זמינות פגיות": ("👶", "kv"),
    'בי"ח פסיכיאטרי תורן': ("🛏️", "duty"),
    "מנהל מרחב תורן": ("🧑‍⚕️", "duty"),
    "חוסרי זמינות נוספים": ("⚠️", "list"),
}
SECTION_HEADERS = set(SECTION_META)  # תאימות לאחור

TITLE = 'זמינות פגיות, מצנתרי מוח ותחומים נוספים\nמד"א ירושלים'

_HEB_DOW = ("יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "שבת", "יום ראשון")
_DUTY_RE = re.compile(r"(\d{1,2}/\d{1,2})(?:/\d{2,4})?\s*בשעה\s*(\d{3,4})")


def _status_emoji(text: str) -> str:
    if "לא זמין" in text or "סגור" in text:
        return "⛔"
    if "זמין" in text:
        return "✅"
    return "▪️"


def _tidy_status(text: str) -> str:
    t = text.replace("יש להעביר דיווח", "דיווח נדרש").strip()
    return re.sub(r"\s*-\s*", " · ", t, count=1) if " - " in t else t


def _duty_time(text: str) -> str | None:
    found = _DUTY_RE.findall(text)
    if len(found) >= 2:
        (d1, h1), (d2, h2) = found[0], found[1]
        f = lambda h: f"{h.zfill(4)[:2]}:{h.zfill(4)[2:]}"  # noqa: E731
        return f"🕗 {d1} {f(h1)} — {d2} {f(h2)}"
    return None


def note(msg: str) -> None:
    """מדפיס לוג וגם כותב לסיכום הריצה של GitHub (נראה בעמוד ה-Action)."""
    print(msg, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(msg.rstrip() + "\n\n")
        except OSError:
            pass


def sheet_id() -> str:
    return os.environ.get("SHEET_ID", DEFAULT_SHEET_ID).strip()


def csv_url() -> str:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id()}/gviz/tq?tqx=out:csv"
    gid = os.environ.get("SHEET_GID", "").strip()
    if gid:
        url += f"&gid={gid}"
    return url


def sheet_link() -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id()}/edit"


def fetch_csv_sync(timeout: int = 20, attempts: int = 3) -> str:
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                csv_url(), headers={"User-Agent": "Mozilla/5.0 (availability-bot)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as err:  # noqa: BLE001
            last_err = err
            if i < attempts - 1:
                time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed to fetch sheet after {attempts} attempts: {last_err}")


def render_board(raw_csv: str) -> str:
    rows = [[c.strip() for c in cell] for cell in csv.reader(io.StringIO(raw_csv))]
    blocks: list[list[str]] = []
    kind = "list"

    def esc(text: str) -> str:
        return html.escape(text, quote=False)  # מותר להשאיר " כפי שהוא בטלגרם

    for row in rows:
        b = row[1] if len(row) > 1 else ""
        c = row[2] if len(row) > 2 else ""
        d = row[3] if len(row) > 3 else ""
        if not any((b, c, d)):
            continue

        if b in SECTION_META:
            emoji, kind = SECTION_META[b]
            blocks.append([f"{emoji} <b>{esc(b)}</b>"])
            continue
        if b == "הערות:":
            continue
        if not blocks:  # שורה לפני הסעיף הראשון
            blocks.append([])

        cur = blocks[-1]

        if kind == "kv" and c:
            cur.append(f"{_status_emoji(c)} {esc(b)} — {esc(_tidy_status(c))}")
        elif kind == "duty" and c:
            cur.append(f"📍 <b>{esc(c)}</b>")
            cur.append(_duty_time(b) or f"🕗 {esc(b.rstrip(': '))}")
        elif kind == "duty":  # שורת הערה חופשית בתוך סעיף תורנות
            cur.append(f"<i>ℹ️ {esc(b)}</i>")
        else:  # list / לא מזוהה
            for part in (p.strip() for p in b.split("\n")):
                if not part:
                    continue
                if part.startswith("("):
                    cur.append(f"<i>{esc(part)}</i>")
                else:
                    cur.append(f"• {esc(part)}" + (f" — {esc(c)}" if c else ""))

    rendered = "\n\n".join("\n".join(bl) for bl in blocks if bl).strip()
    return rendered or "לא נמצאו נתונים בגיליון."


def build_board_text(raw_csv: str, fetched_at: datetime | None) -> str:
    if fetched_at:
        stamp = f"{_HEB_DOW[fetched_at.weekday()]}, {fetched_at:%d/%m}, {fetched_at:%H:%M}"
    else:
        stamp = "—"
    return (
        '🏥 <b>מד"א ירושלים — לוח זמינות</b>\n'
        f"🕐 עודכן: {stamp}\n\n"
        f"{render_board(raw_csv)}\n\n"
        f'<a href="{html.escape(sheet_link())}">↗ פתיחת הגיליון המלא</a>'
    )
