@echo off
chcp 65001 >nul
title ICSautoScaleUpdater - build
echo ============================================
echo   Aftomati enimerosi zygon - build
echo ============================================
echo.

rem To onoma (live i beta) vgainei apo to APP_BUILD tou autohost.py.
set APPNAME=ICSautoScaleUpdater
findstr /R /C:"^APP_BUILD = \"[^\"]*beta" autohost.py >nul 2>&1 && set APPNAME=ICSautoScaleUpdater-beta
echo Efarmogi: %APPNAME%

echo [1/4] Kleisimo tou programmatos an trexei...
taskkill /F /IM %APPNAME%.exe >nul 2>&1
taskkill /F /IM AutoHost.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/4] Egkatastasi vivliothikon...
python -m pip install --upgrade --quiet "pyinstaller==6.21.0" pystray Pillow
if errorlevel 1 goto :pyerror

echo [3/4] Katharismos palion build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %APPNAME%.spec del /q %APPNAME%.spec
if exist AutoHost.spec del /q AutoHost.spec

echo [4/4] Build...
pyinstaller --noconfirm --onedir --windowed --name %APPNAME% ^
  --icon logo.ico ^
  --add-data "config_default.json;." ^
  --add-data "logo.png;." ^
  --add-data "logo.ico;." ^
  autohost.py
if errorlevel 1 goto :builderror

echo.
echo ============================================
echo   ETOIMO: dist\%APPNAME%\%APPNAME%.exe
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
echo An leei PermissionError: kleise to ICSautoScaleUpdater.exe kai xanatrexe.

:end
pause
