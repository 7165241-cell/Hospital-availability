@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] יוצר סביבה וירטואלית ומתקין תלויות...
  py -m venv .venv || goto :err
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
)

if not exist ".env" (
  echo.
  echo  לא נמצא קובץ .env
  echo  העתיקי את .env.example ל-.env ומלאי את BOT_TOKEN מ-@BotFather
  echo.
  pause
  exit /b 1
)

echo [run] מפעיל את הבוט... (סגירת החלון עוצרת אותו)
".venv\Scripts\python.exe" bot.py
goto :eof

:err
echo.
echo  ההתקנה נכשלה. ודאי ש-Python מותקן (py --version).
pause
exit /b 1
