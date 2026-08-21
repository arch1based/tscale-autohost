@echo off
chcp 65001 >nul
title ICSautoScaleUpdater - dimosiefsi neas ekdosis
set /p VER=Neos arithmos ekdosis (px 1.1.0): 
set /p NOTES=Ti allakse: 
python release.py %VER% "%NOTES%"
pause
