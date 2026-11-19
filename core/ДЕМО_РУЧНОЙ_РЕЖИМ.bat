@echo off
rem =========================================================
rem Launch 50/50 Split Screen for Manual Testing
rem =========================================================
chcp 65001 >nul
cd /d "%~dp0"

where wt.exe >nul 2>&1
if not errorlevel 1 (
    start wt.exe -M --title "Geely HU Interactive Stand" -d "%~dp0" cmd /k "chcp 65001 >nul & title Эмулятор ГУ (Слева) & python emulator.py" ; split-pane -V -d "%~dp0\.." cmd /k "chcp 65001 >nul & title Geely ADB Unlock Master (Справа) & СТАРТ_Windows.bat"
    exit /b 0
)

rem Fallback for standard CMD without Windows Terminal
start "Эмулятор ГУ (Слева)" cmd /k "chcp 65001 >nul & python emulator.py"
timeout /t 1 /nobreak >nul
start "Geely ADB Unlock Master (Справа)" cmd /k "chcp 65001 >nul & cd .. & СТАРТ_Windows.bat"
