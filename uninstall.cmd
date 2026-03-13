@echo off
title Functionmap Uninstall
color 0F

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
set EXITCODE=%errorlevel%
echo.
pause
exit /b %EXITCODE%
