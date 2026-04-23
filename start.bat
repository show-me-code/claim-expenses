@echo off
title Expense System

cd /d %~dp0

if not exist uploads mkdir uploads
if not exist output mkdir output

start "Backend" cmd /k cd src\backend && python app.py

timeout /t 6 /nobreak >nul

start http://localhost:5000

echo System started!
echo Browser will open automatically.
echo.
echo Close this window when done.
pause