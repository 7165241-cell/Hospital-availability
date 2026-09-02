# פריסה חינמית — ערוץ טלגרם + GitHub Actions

השיטה היחידה שהיא **חינם לגמרי, בלי כרטיס אשראי, ויציבה**:
GitHub מריץ סקריפט קטן פעם ביום ב-08:15 (שעון ישראל), שקורא את הגיליון
ושולח את הלוח לערוץ טלגרם שכולם מצטרפים אליו.

בלי מחשב שדולק, בלי שרת.

מה מפסידים: אין כפתור "עדכון עכשיו" — רק הפוסט היומי (אפשר להוסיף עוד שעות ביום).

---

## שלב 1 — יצירת ערוץ והוספת הבוט כמנהל

1. בטלגרם: תפריט ➜ **ערוץ חדש** (New Channel). שם: `זמינות מד"א ירושלים`.
2. סוג הערוץ: **ציבורי**, ותנו כתובת קצרה, למשל `mda_jlm_availability`.
   (הכתובת הזו = הקישור להצטרפות: `t.me/mda_jlm_availability`)
3. אחרי היצירה: הגדרות הערוץ ➜ **מנהלים** ➜ **הוספת מנהל** ➜ מחפשים
   `@hospital_availability_bot` ומוסיפים. מספיקה הרשאת **"פרסום הודעות"**.

> אם עדיף ערוץ פרטי: ה-`CHANNEL_ID` יהיה מספר (מוסבר בשלב 3).

---

## שלב 2 — יצירת ה-repo בגיטהאב

1. github.com ➜ **New repository** ➜ שם `mda-availability-bot` ➜ Private ➜ Create.
2. מעלים לתוכו את **תוכן** התיקייה הזו כך שהקבצים יהיו בשורש ה-repo
   (`bot.py`, `board.py`, `daily_post.py`, `requirements.txt`, `.github/…`).

   הכי פשוט מ-PowerShell בתוך התיקייה:

   ```powershell
   git init
   git add board.py daily_post.py bot.py requirements.txt README.md DEPLOY.md .github .gitignore .env.example
   git commit -m "בוט זמינות מד״א ירושלים"
   git branch -M main
   git remote add origin https://github.com/<שם-המשתמש>/mda-availability-bot.git
   git push -u origin main
   ```

   ⚠️ אל תעלו את `.env` ואת `subscribers.db` — הם כבר ב-`.gitignore`.

---

## שלב 3 — הגדרת ה-Secrets

ב-repo: **Settings ➜ Secrets and variables ➜ Actions ➜ New repository secret**.
מוסיפים שניים:

| שם | ערך |
|----|-----|
| `BOT_TOKEN` | הטוקן מ-@BotFather (`8861580099:AAH…`) |
| `CHANNEL_ID` | `@mda_jlm_availability` (או המספר `-100…` לערוץ פרטי) |

**איך משיגים מספר של ערוץ פרטי:** מוסיפים לערוץ את `@getidsbot` לרגע,
הוא שולח מספר בסגנון `-1001234567890`, מסירים אותו, ומשתמשים במספר.

---

## שלב 4 — בדיקה

ב-repo: **Actions ➜ daily-availability-post ➜ Run workflow** (משאירים "force" מסומן).
תוך דקה אמור להופיע פוסט בערוץ. אם לא — פותחים את הריצה ורואים את השגיאה בלוג.

מכאן זה אוטומטי כל בוקר ב-08:15.

---

## הערות ומגבלות

* ריצות מתוזמנות ב-GitHub עלולות להתעכב ב-5–15 דקות בשעות עומס — לא מדויק לשנייה.
* GitHub **משבית** workflow מתוזמן אחרי 60 יום בלי פעילות ב-repo. כדי למנוע:
  להיכנס פעם בחודש ל-Actions וללחוץ Run, או לדחוף commit קטן.
* רוצים עדכון גם בצהריים ובערב? מוסיפים שורות `cron` ב-`.github/workflows/daily.yml`
  ומעדכנים את הבדיקה ב-`daily_post.py` (או פשוט מריצים תמיד עם `FORCE=1`).
* הבוט האינטראקטיבי (`bot.py`, עם כפתורים ו-`/start`) עדיין נמצא ב-repo והוא
  אופציונלי — הוא דורש מחשב/שרת שדולק תמיד עם גישה לטלגרם, ולכן לא חלק
  מהפריסה החינמית.
