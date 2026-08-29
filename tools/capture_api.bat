@echo off
chcp 65001 >nul
title Καταγραφή επικοινωνίας AutoProcess - ζυγού
echo ================================================================
echo   ΚΑΤΑΓΡΑΦΗ: πως μιλαει το AutoProcess στον ζυγο
echo ================================================================
echo.
echo Θα καταγραψουμε ολη την κινηση δικτυου οσο τρεχει το AutoProcess.
echo Μετα θα εχουμε το ακριβες αιτημα HTTP που στελνει στον ζυγο.
echo.
echo ΠΡΟΣΟΧΗ: τρεξε αυτο το αρχειο ως Διαχειριστης (δεξι κλικ - Εκτελεση ως διαχειριστης)
echo.
pause

set OUT=%~dp0capture
if not exist "%OUT%" mkdir "%OUT%"

echo.
echo [1/4] Εναρξη καταγραφης...
netsh trace start capture=yes tracefile="%OUT%\autoprocess.etl" maxsize=200 overwrite=yes report=no
if errorlevel 1 goto :noadmin

echo.
echo [2/4] ΤΩΡΑ: ανοιξε το AutoProcess και στειλε στον ζυγο.
echo       Περιμενε να δεις "send success" ή "send fail" στο log του.
echo.
pause

echo.
echo [3/4] Τερματισμος καταγραφης (θελει 1-2 λεπτα, μην κλεισεις το παραθυρο)...
netsh trace stop

echo.
echo [4/4] Συγκεντρωση στοιχειων...
ipconfig /all > "%OUT%\network.txt" 2>&1
arp -a >> "%OUT%\network.txt" 2>&1
netstat -ano >> "%OUT%\network.txt" 2>&1
copy /y "%~dp0..\ip.xml" "%OUT%\" >nul 2>&1
copy /y "%~dp0..\settings.xml" "%OUT%\" >nul 2>&1
if exist "%~dp0..\log" xcopy /y /q "%~dp0..\log\*.txt" "%OUT%\log\" >nul 2>&1

echo.
echo ================================================================
echo   ΕΤΟΙΜΟ. Στειλε ολο τον φακελο: %OUT%
echo ================================================================
echo.
echo Αρχεια: autoprocess.etl (η καταγραφη), network.txt, ip.xml, log
echo.
goto :end

:noadmin
echo.
echo ΣΦΑΛΜΑ: χρειαζεται δικαιωματα Διαχειριστη.
echo Κλεισε το, δεξι κλικ στο αρχειο - "Εκτελεση ως διαχειριστης".

:end
pause
