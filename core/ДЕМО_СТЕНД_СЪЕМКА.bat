@echo off
rem =========================================================
rem Launch 50/50 Split Screen Demo for Video Recording
rem =========================================================
chcp 65001 >nul
cd /d "%~dp0"

where wt.exe >nul 2>&1
if not errorlevel 1 (
    start wt.exe -M --title "Geely HU Stand Demo" -d "%~dp0" cmd /k "chcp 65001 >nul & title Эмулятор ГУ (Стенд) & python emulator.py" ; split-pane -V -d "%~dp0" cmd /k "chcp 65001 >nul & title Авто-Демонстрация & python demo_live.py"
    exit /b 0
)

rem Fallback for standard CMD without Windows Terminal
start "Эмулятор ГУ (Слева)" cmd /k "chcp 65001 >nul & python emulator.py"
timeout /t 1 /nobreak >nul
start "Авто-Демонстрация (Справа)" cmd /k "chcp 65001 >nul & python demo_live.py"
