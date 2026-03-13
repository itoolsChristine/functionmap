@echo off
title Functionmap Sync
color 0F

:: Find Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=python
    goto :run
)
where python3 >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=python3
    goto :run
)

echo.
echo  ERROR: Python not found.
echo  Install Python 3.8+ and ensure it is in your PATH.
echo.
pause
exit /b 1

:run
%PYTHON% "%~dp0sync.py" %*
set EXITCODE=%errorlevel%
echo.
pause
exit /b %EXITCODE%
