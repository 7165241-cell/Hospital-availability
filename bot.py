"""
בוט טלגרם — זמינות פגיות, מצנתרי מוח ותחומים נוספים | מד"א ירושלים.

מה הבוט עושה:
  • כל אחד יכול להתחבר אליו (/start) — אין רשימת מורשים.
  • הנתונים נקראים *ישירות* מהגיליון המשותף בכל בקשה, אז הם תמיד מעודכנים.
  • מי שמתחבר נרשם אוטומטית לעדכון יומי, שנשלח פעם ביום בשעה קבועה
    (ברירת מחדל 08:15, שעון ישראל) — עם כפתור לביטול.
  • כפתור «📋 מצב נוכחי» / «🔄 רענון» מושך את הלוח העדכני עכשיו.

הרצה:  python bot.py   (אחרי pip install -r requirements.txt ומילוי .env)
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

import board
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("mda-availability-bot")

# ------------------------------------------------------------------ הגדרות מ-.env
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
SHEET_ID = os.environ.get(
    "SHEET_ID", "1ybPhMiIba43GawAzHNl9AJiMCBi61t4NWhQuXCYVwag"
).strip()
SHEET_GID = os.environ.get("SHEET_GID", "").strip()
TZ_NAME = os.environ.get("TZ", "Asia/Jerusalem").strip()
DAILY_HOUR = int(os.environ.get("DAILY_HOUR", "8"))
DAILY_MINUTE = int(os.environ.get("DAILY_MINUTE", "15"))
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "60"))
PROXY_URL = os.environ.get("PROXY_URL", "").strip()  # אם api.telegram.org חסום ברשת

TZ = ZoneInfo(TZ_NAME)
DB_PATH = Path(__file__).with_name("subscribers.db")

BTN_STATUS = "📋 מצב נוכחי"
BTN_SUB_ON = "🔔 הפעלת עדכון יומי"
BTN_SUB_OFF = "🔕 ביטול עדכון יומי"


# ------------------------------------------------------------------ בסיס נתונים
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id    INTEGER PRIMARY KEY,
            title      TEXT,
            subscribed INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def set_subscription(chat_id: int, title: str | None, subscribed: bool) -> None:
    now = datetime.now(TZ).isoformat(timespec="seconds")
    with closing(db()) as conn, conn:
        conn.execute(
            """
            INSERT INTO subscribers (chat_id, title, subscribed, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = COALESCE(excluded.title, subscribers.title),
                subscribed = excluded.subscribed,
                updated_at = excluded.updated_at
            """,
            (chat_id, title, int(subscribed), now),
        )


def is_subscribed(chat_id: int) -> bool:
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT subscribed FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return bool(row and row[0])


def subscribed_chat_ids() -> list[int]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT chat_id FROM subscribers WHERE subscribed = 1"
        ).fetchall()
    return [r[0] for r in rows]


# ------------------------------------------------------------------ קריאת הגיליון
_cache: dict[str, object] = {"ts": 0.0, "text": "", "fetched_at": None}


async def fetch_csv() -> str:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(board.csv_url())
        resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


async def build_message(force: bool = False) -> str:
    now = time.monotonic()
    if not force and _cache["text"] and now - float(_cache["ts"]) < CACHE_TTL:
        raw = str(_cache["text"])
        fetched_at = _cache["fetched_at"]
    else:
        try:
            raw = await fetch_csv()
            fetched_at = datetime.now(TZ)
            _cache.update(ts=now, text=raw, fetched_at=fetched_at)
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch failed: %s", exc)
            if _cache["text"]:
                raw = str(_cache["text"])
                fetched_at = _cache["fetched_at"]
            else:
                return (
                    "⚠️ לא הצלחתי לקרוא את הגיליון כרגע. נסו שוב עוד רגע.\n"
                    f'<a href="{html.escape(board.sheet_link())}">פתיחת הגיליון</a>'
                )

    return board.build_board_text(raw, fetched_at)


# ------------------------------------------------------------------ מקלדות
def main_keyboard(subscribed: bool) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_STATUS)],
            [KeyboardButton(BTN_SUB_OFF if subscribed else BTN_SUB_ON)],
        ],
        resize_keyboard=True,
    )


REFRESH_MARKUP = InlineKeyboardMarkup(
    [[InlineKeyboardButton("🔄 רענון", callback_data="refresh")]]
)


async def send_board(update: Update, context: ContextTypes.DEFAULT_TYPE, force: bool):
    text = await build_message(force=force)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=REFRESH_MARKUP,
    )


# ------------------------------------------------------------------ handlers
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    set_subscription(chat.id, chat.title or chat.full_name, True)
    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            "שלום! 👋\n"
            "הבוט מציג את לוח הזמינות היומי של מד\"א ירושלים "
            "(פגיות, מצנתרי מוח, בי\"ח פסיכיאטרי תורן, מנהל מרחב תורן ועוד).\n\n"
            f"נרשמת לעדכון יומי אוטומטי בשעה "
            f"{DAILY_HOUR:02d}:{DAILY_MINUTE:02d}. "
            "אפשר לבטל בכל רגע עם הכפתור למטה.\n\n"
            "לצפייה עכשיו — «📋 מצב נוכחי»."
        ),
        reply_markup=main_keyboard(True),
    )
    await send_board(update, context, force=False)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "פקודות:\n"
        "/start — התחברות + הרשמה לעדכון יומי\n"
        "/status — הצגת הלוח העדכני\n"
        "/subscribe — הפעלת עדכון יומי\n"
        "/unsubscribe — ביטול עדכון יומי\n\n"
        f"העדכון היומי נשלח בשעה {DAILY_HOUR:02d}:{DAILY_MINUTE:02d} (שעון ישראל).",
        reply_markup=main_keyboard(is_subscribed(update.effective_chat.id)),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_board(update, context, force=False)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    set_subscription(chat.id, chat.title or chat.full_name, True)
    await update.effective_message.reply_text(
        f"✅ נרשמת. תקבלו את הלוח כל יום ב-{DAILY_HOUR:02d}:{DAILY_MINUTE:02d}.",
        reply_markup=main_keyboard(True),
    )


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    set_subscription(chat.id, chat.title or chat.full_name, False)
    await update.effective_message.reply_text(
        "🔕 העדכון היומי בוטל. אפשר להמשיך לבדוק ידנית עם «📋 מצב נוכחי».",
        reply_markup=main_keyboard(False),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.effective_message.text or "").strip()
    if txt == BTN_STATUS:
        await send_board(update, context, force=False)
    elif txt == BTN_SUB_ON:
        await cmd_subscribe(update, context)
    elif txt == BTN_SUB_OFF:
        await cmd_unsubscribe(update, context)


async def on_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("מרענן…")
    text = await build_message(force=True)
    try:
        await query.edit_message_text(
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=REFRESH_MARKUP,
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    text = await build_message(force=True)
    sent = failed = 0
    for chat_id in subscribed_chat_ids():
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent += 1
        except Forbidden:
            set_subscription(chat_id, None, False)
            failed += 1
        except BadRequest as exc:
            log.warning("daily_push to %s failed: %s", chat_id, exc)
            failed += 1
        await asyncio.sleep(0.05)
    log.info("daily_push done: sent=%d failed=%d", sent, failed)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("handler error", exc_info=context.error)


# ------------------------------------------------------------------ main
async def post_init(app: Application):
    await app.bot.set_my_commands(
        [
            ("start", "התחברות + עדכון יומי"),
            ("status", "הצגת הלוח העדכני"),
            ("subscribe", "הפעלת עדכון יומי"),
            ("unsubscribe", "ביטול עדכון יומי"),
            ("help", "עזרה"),
        ]
    )


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "חסר BOT_TOKEN. העתיקו את .env.example ל-.env ומלאו את הטוקן מ-@BotFather."
        )

    builder = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
        log.info("using proxy for Telegram: %s", PROXY_URL)
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CallbackQueryHandler(on_refresh, pattern="^refresh$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    app.job_queue.run_daily(
        daily_push,
        time=dtime(hour=DAILY_HOUR, minute=DAILY_MINUTE, tzinfo=TZ),
        name="daily_push",
    )

    log.info(
        "starting — daily push at %02d:%02d %s, sheet %s",
        DAILY_HOUR,
        DAILY_MINUTE,
        TZ_NAME,
        SHEET_ID,
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
