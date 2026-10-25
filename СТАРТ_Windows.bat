@echo off
cd /d "%~dp0"

echo ===================================================
echo   Starting Geely ADB Unlock Master...
echo ===================================================
echo.

title Geely ADB Unlock Master

if exist "core\geely_unlock.exe" (
    "core\geely_unlock.exe"
    exit /b 0
)

where python >nul 2>&1
if not errorlevel 1 (
    python "core\main.py"
    exit /b 0
)

where py >nul 2>&1
if not errorlevel 1 (
    py "core\main.py"
    exit /b 0
)

echo ERROR: Neither core\geely_unlock.exe nor Python was found.
pause
exit /b 1
