@echo off
rem =========================================================
rem Launch 50/50 Split Screen for Manual Testing
rem =========================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Launching Geely HU Stand in manual mode...
where wt.exe >nul 2>&1
if not errorlevel 1 (
    start wt.exe --title "Geely HU Interactive Stand" -d . cmd /k python emulator.py ^; split-pane -V -d .. cmd /k ..\СТАРТ_Windows.bat
    exit /b 0
)

rem Fallback if wt.exe is not available: open 2 separate windows
start "Geely HU Emulator (Left)" cmd /k python emulator.py
timeout /t 1 /nobreak >nul
start "Geely ADB Unlock Master (Right)" cmd /k cd .. ^& СТАРТ_Windows.bat
