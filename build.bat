@echo off
REM Δημιουργία AutoHost.exe (χρειάζεται Python 3.9+ στα Windows)
python -m pip install --upgrade pyinstaller pystray Pillow
pyinstaller --noconfirm --onefile --windowed --name AutoHost ^
  --icon logo.ico ^
  --add-data "config_default.json;." ^
  --add-data "logo.png;." ^
  --add-data "logo.ico;." ^
  autohost.py
echo.
echo Το .exe βρίσκεται στον φάκελο dist\AutoHost.exe
pause
