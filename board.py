"""
לוגיקת קריאה ועיצוב של לוח הזמינות — ספרייה סטנדרטית בלבד (בלי תלויות).
משמש גם את bot.py (הבוט האינטראקטיבי) וגם את daily_post.py (GitHub Actions).
"""

from __future__ import annotations

import csv
import html
import io
import os
import urllib.request
from datetime import datetime

DEFAULT_SHEET_ID = "1ybPhMiIba43GawAzHNl9AJiMCBi61t4NWhQuXCYVwag"

# כותרות הסעיפים בגיליון — נשארות קבועות גם כשהתוכן משתנה כל יום.
SECTION_HEADERS = {
    "זמינות מצנתר מוח",
    "זמינות פגיות",
    'בי"ח פסיכיאטרי תורן',
    "מנהל מרחב תורן",
    "חוסרי זמינות נוספים",
}

TITLE = 'זמינות פגיות, מצנתרי מוח ותחומים נוספים\nמד"א ירושלים'


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


def fetch_csv_sync(timeout: int = 20) -> str:
    with urllib.request.urlopen(csv_url(), timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def render_board(raw_csv: str) -> str:
    rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(raw_csv))]
    n = len(rows)
    lines: list[str] = []

    for i, row in enumerate(rows):
        b = row[1] if len(row) > 1 else ""
        c = row[2] if len(row) > 2 else ""
        d = row[3] if len(row) > 3 else ""

        if not any((b, c, d)):
            continue

        if b in SECTION_HEADERS:
            if lines:
                lines.append("")
            lines.append(f"<b>{html.escape(b)}</b>")
            continue

        if b == "הערות:":
            nxt = rows[i + 1][1].strip() if i + 1 < n and len(rows[i + 1]) > 1 else ""
            if nxt and nxt not in SECTION_HEADERS and nxt != "הערות:":
                lines.append("<i>הערות:</i>")
            continue

        extra = " | ".join(x for x in (c, d) if x)
        if extra:
            lines.append(f"• {html.escape(b)} — {html.escape(extra)}")
        else:
            lines.append(html.escape(b))

    return "\n".join(lines).strip() or "לא נמצאו נתונים בגיליון."


def build_board_text(raw_csv: str, fetched_at: datetime | None) -> str:
    stamp = fetched_at.strftime("%d/%m/%Y %H:%M") if fetched_at else "—"
    return (
        f"🏥 <b>{html.escape(TITLE)}</b>\n"
        f"🕒 נכון ל-{stamp}\n\n"
        f"{render_board(raw_csv)}\n\n"
        f'<a href="{html.escape(sheet_link())}">מקור: הגיליון המשותף</a>'
    )
