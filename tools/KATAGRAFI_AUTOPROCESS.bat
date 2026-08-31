@echo off
chcp 65001 >nul
title Καταγραφη - τι ακριβως στελνει το AutoProcess
cls
echo ================================================================
echo    ΚΑΤΑΓΡΑΦΗ ΩΜΩΝ BYTES ΑΠΟ ΤΟ AutoProcess
echo ================================================================
echo.
echo Το AutoProcess θα στειλει σε ΕΜΑΣ αντι για τον ζυγο, και κραταμε
echo τα bytes ΑΥΤΟΥΣΙΑ. Ο πραγματικος ζυγος δεν πειραζεται καθολου.
echo.
echo ΠΡΟΣΟΧΗ: μην αντιγραψεις το αποτελεσμα απο την οθονη - η αντιγραφη
echo καταστρεφει ακριβως την πληροφορια που ψαχνουμε. Στειλε το αρχειο.
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo ΣΦΑΛΜΑ: δεν βρεθηκε η Python.
  echo Κατεβασε την απο python.org και τσεκαρε "Add python.exe to PATH".
  pause
  exit /b 1
)

set APDIR=%~dp0
if not exist "%APDIR%ip.xml" set APDIR=%~dp0..\
if not exist "%APDIR%ip.xml" (
  echo ΣΦΑΛΜΑ: δεν βρεθηκε το ip.xml.
  echo Βαλε αυτο το αρχειο ΜΕΣΑ στον φακελο του AutoProcess και ξανατρεξε.
  pause
  exit /b 1
)

echo [1/4] Φυλαξη του ip.xml...
copy /y "%APDIR%ip.xml" "%APDIR%ip.xml.bak" >nul
echo ^<?xml version="1.0" encoding="utf-8"?^> > "%APDIR%ip.xml"
echo ^<ips^> >> "%APDIR%ip.xml"
echo   ^<ip^>127.0.0.1^</ip^> >> "%APDIR%ip.xml"
echo ^</ips^> >> "%APDIR%ip.xml"

echo [2/4] Εκκινηση καταγραφης στη θυρα 1235...
start "Καταγραφη" cmd /c python "%~dp0raw_capture.py" ^> "%~dp0katagrafi.bin"
timeout /t 3 /nobreak >nul

echo.
echo [3/4] ΤΩΡΑ:
echo       - Ανοιξε το AutoProcess
echo       - Πατα Start / αποστολη, οπως παντα
echo       - Περιμενε να γραψει "send success" στο log του
echo.
pause

echo [4/4] Επαναφορα του ip.xml...
copy /y "%APDIR%ip.xml.bak" "%APDIR%ip.xml" >nul
del "%APDIR%ip.xml.bak" >nul 2>&1

echo.
echo ================================================================
echo   ΑΠΟΤΕΛΕΣΜΑ
echo ================================================================
python "%~dp0analysi_katagrafis.py" "%~dp0katagrafi.bin"
echo.
echo Το αρχειο: %~dp0katagrafi.bin
echo Στειλε το ΩΣ ΑΡΧΕΙΟ (οχι αντιγραφη κειμενου).
pause
