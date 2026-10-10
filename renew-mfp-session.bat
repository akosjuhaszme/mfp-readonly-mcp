@echo off
chcp 65001 >nul
title MyFitnessPal munkamenet megújítása
echo.
echo  MyFitnessPal munkamenet megújítása
echo  ----------------------------------
echo  1. Megnyílik a MyFitnessPal a böngészőben. Jelentkezz be, ha kéri.
echo  2. Nyomd meg az F12-t, majd: Alkalmazás - Tárolás - Cookie-k - myfitnesspal.com
echo  3. A  __Secure-next-auth.session-token  sorban kattints duplán az ÉRTÉK mezőre,
echo     jelöld ki az egészet (Ctrl+A) és másold ki (Ctrl+C).
echo  4. Gyere vissza ide, és a kérdésnél illeszd be (Ctrl+V). Beírás közben semmi
echo     nem látszik - ez normális. Enter.
echo.
echo  A sütit ne másold be sehova máshova (chat, fájl): teljes fiókhozzáférést ad.
echo.
if not defined MFP_NO_BROWSER start "" "https://www.myfitnesspal.com/"
"%~dp0.venv\Scripts\myfitnesspal-mcp.exe" auth
echo.
"%~dp0.venv\Scripts\myfitnesspal-mcp.exe" auth --check
echo.
echo  Ha fent "Status: valid" szerepel, kész - újraindítani semmit nem kell.
echo.
pause
