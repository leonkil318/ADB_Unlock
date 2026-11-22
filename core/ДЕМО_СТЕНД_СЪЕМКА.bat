@echo off
rem =========================================================
rem Launch 50/50 Split Screen Demo for Video Recording
rem =========================================================
chcp 65001 >nul
cd /d "%~dp0"

rem Clean up any stale emulator session files
del /f /q .emulator_port .emulator_state.json >nul 2>&1

echo [1/2] Launching Geely HU Demo Stand...
where wt.exe >nul 2>&1
if not errorlevel 1 (
    start wt.exe --title "Geely HU Stand Demo" -d . cmd /k python emulator.py --watch ^; split-pane -V -d . cmd /k python demo_live.py
    exit /b 0
)

rem Fallback if wt.exe is not available: open 2 separate windows
start "Geely HU Emulator (Left)" cmd /k python emulator.py --watch
timeout /t 1 /nobreak >nul
start "Geely Unlock Demo (Right)" cmd /k python demo_live.py
