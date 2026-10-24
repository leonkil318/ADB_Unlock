@echo off
cd /d "%~dp0"

echo ===================================================
echo   Geely ADB Unlock Master - TEST SIMULATOR
echo ===================================================
echo.
echo Launching safe simulation mode (no hardware required)...
echo Real vehicle and system files are NOT touched.
echo.

where python >nul 2>&1
if not errorlevel 1 (
    python "core\test\server_sim.py"
    exit /b 0
)

where py >nul 2>&1
if not errorlevel 1 (
    py "core\test\server_sim.py"
    exit /b 0
)

echo ERROR: Python is required to run test simulation mode.
pause
exit /b 1
