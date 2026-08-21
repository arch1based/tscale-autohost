@echo off
chcp 65001 >nul
title AutoHost - build
echo ============================================
echo   T-Scale AUTO HOST - dimiourgia AutoHost.exe
echo ============================================
echo.

echo [1/4] Kleisimo tou AutoHost.exe an trexei...
taskkill /F /IM AutoHost.exe >nul 2>&1
if %errorlevel%==0 (echo      - to palio AutoHost.exe ekleise) else (echo      - den etrexe)
timeout /t 2 /nobreak >nul

echo [2/4] Egkatastasi vivliothikon...
python -m pip install --upgrade --quiet pyinstaller pystray Pillow
if errorlevel 1 goto :pyerror

echo [3/4] Katharismos palion build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist AutoHost.spec del /q AutoHost.spec

echo [4/4] Build...
pyinstaller --noconfirm --onefile --windowed --name AutoHost ^
  --icon logo.ico ^
  --add-data "config_default.json;." ^
  --add-data "logo.png;." ^
  --add-data "logo.ico;." ^
  autohost.py
if errorlevel 1 goto :builderror

echo.
echo ============================================
echo   ETOIMO: dist\AutoHost.exe
echo ============================================
echo.
choice /c YN /n /m "Na anoixei o fakelos dist? (Y/N) "
if errorlevel 2 goto :end
explorer "%cd%\dist"
goto :end

:pyerror
echo.
echo SFALMA: den vrethike i Python i apetyche to pip install.
echo Egkatastise Python 3.12 apo python.org me tin epilogi "Add python.exe to PATH".
goto :end

:builderror
echo.
echo SFALMA sto build. Stile tis teleftaies grammes gia elegxo.
echo An leei PermissionError: kleise to AutoHost.exe (kai to eikonidio kato dexia) kai xanatrexe.

:end
pause
