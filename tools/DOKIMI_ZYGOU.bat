@echo off
chcp 65001 >nul
title Καταγραφη πρωτοκολλου ζυγου
cls
echo ================================================================
echo    ΚΑΤΑΓΡΑΦΗ: τι ακριβως στελνει το AutoProcess στον ζυγο
echo ================================================================
echo.
echo Θα βαλουμε το AutoProcess να στειλει σε ΕΜΑΣ αντι για τον ζυγο.
echo Ολα γινονται τοπικα - ο πραγματικος ζυγος δεν πειραζεται.
echo.

rem --- ελεγχος Python ---
python --version >nul 2>&1
if errorlevel 1 (
  echo ΣΦΑΛΜΑ: δεν βρεθηκε η Python.
  echo Κατεβασε την απο python.org και τσεκαρε "Add python.exe to PATH".
  pause
  exit /b 1
)

rem --- βρες το ip.xml ---
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

echo [2/4] Εκκινηση ψευτικου ζυγου...
start "Ψευτικος ζυγος" cmd /k python "%~dp0fake_scale.py"
timeout /t 3 /nobreak >nul

echo.
echo [3/4] ΤΩΡΑ:
echo       - Ανοιξε το AutoProcess
echo       - Πατα Start / αποστολη, οπως παντα
echo       - Περιμενε να γραψει κατι στο log του
echo.
echo       Στο αλλο παραθυρο θα δεις το αιτημα να καταγραφεται.
echo.
pause

echo [4/4] Επαναφορα του ip.xml...
copy /y "%APDIR%ip.xml.bak" "%APDIR%ip.xml" >nul
del "%APDIR%ip.xml.bak" >nul 2>&1

echo.
echo ================================================================
echo   ΕΤΟΙΜΟ. Στειλε το αρχειο:
echo   %~dp0katagrafi_zygou.txt
echo ================================================================
echo.
echo Κλεισε και το παραθυρο του ψευτικου ζυγου (Ctrl+C).
pause
