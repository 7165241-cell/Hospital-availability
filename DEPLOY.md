# איך זה עובד (פרוס ופעיל)

repo: **github.com/7165241-cell/Hospital-availability**
ערוץ: **"זמינות בתי חולים"** (פרטי) — ה-`CHANNEL_ID` המספרי שמור ב-Secret
בוט: **@hospital_availability_bot**

הכול רץ על השרתים של GitHub — לא צריך מחשב שדולק.

---

## מה רץ

### `bot-tick` (`.github/workflows/poll.yml`) — כל 5 דקות
1. **`bot_poll.py`** — כל מי ששולח הודעה ל-@hospital_availability_bot מקבל בחזרה
   מיד את הלוח העדכני ("עדכון עכשיו").
2. **`watch_sheet.py`** — שולח את הלוח לערוץ כאשר:
   * תוכן הגיליון השתנה → שליחה מיידית עם כותרת "🔔 עדכון בלוח הזמינות".
   * הגיע מועד שליחה קבוע — **07:30 / 15:30 / 23:30** שעון ישראל (בערך; תלוי בעיכובי
     GitHub, ±15 דק') → שליחת הלוח הנוכחי.
     לשינוי המועדים: Secret/Variable בשם `POST_TIMES`, למשל `07:00,13:00,20:00`.
3. שומר את המצב ב-`state/board_state.json` (commit אוטומטי ב-repo).

### `keepalive` (`.github/workflows/keepalive.yml`) — פעם בחודש
commit ריק, כדי ש-GitHub לא ישבית את ה-workflows אחרי 60 יום. אוטומטי לגמרי.

---

## מה צריך לוודא פעם אחת

* **ה-repo חייב להיות Public** — ריצה כל 5 דק' אוכלת את דקות ה-Actions של repo פרטי.
  Settings ➜ General ➜ למטה ➜ Change visibility ➜ Public.
  (אין סודות בקוד. `BOT_TOKEN` נשאר מוצפן ב-Secrets גם ב-repo ציבורי.)
  להשאיר פרטי? לשנות ב-`poll.yml` את `*/5` ל-`*/15`.
* **Secrets** (Settings ➜ Secrets and variables ➜ Actions): `BOT_TOKEN`, `CHANNEL_ID`.
* **להצמיד בערוץ**: *"📩 לעדכון מיידי — שלחו הודעה ל-@hospital_availability_bot"*.

---

## הערות

* ריצות מתוזמנות ב-GitHub מתעכבות לפעמים 5–15 דק' בעומס — לא מדויק לשנייה.
* להריץ ידנית לבדיקה: Actions ➜ bot-tick ➜ Run workflow.
* `daily_post.py` — שליחה ידנית חד-פעמית של הלוח לערוץ (לא בשימוש אוטומטי).
* `bot.py` — הבוט האינטראקטיבי המלא (כפתורים, `/start`, מנוי). אופציונלי,
  דורש מחשב/שרת שדולק תמיד. לא חלק מהפריסה.
* אם צריך להחליף טוקן: `/token` ב-@BotFather, ואז לעדכן את ה-Secret `BOT_TOKEN`.
