@echo off
title Stop Server

taskkill /F /FI "WINDOWTITLE eq Backend*" >nul 2>&1

echo Server stopped.
pause