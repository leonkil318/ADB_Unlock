@echo off
rem =========================================================
rem Launch 50/50 Split Screen Demo for Video Recording
rem =========================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Запуск демонстрационного стенда Geely...
wt.exe --title "Geely HU Stand Demo" -d "%~dp0" cmd /k "chcp 65001 >nul & title Эмулятор ГУ (Стенд) & python emulator.py --watch" ^; split-pane -V -d "%~dp0" cmd /k "chcp 65001 >nul & title Авто-Демонстрация & python demo_live.py"
if not errorlevel 1 exit /b 0

rem Fallback if wt.exe is not available: open 2 separate classic windows
start "Эмулятор ГУ (Слева)" cmd /k "chcp 65001 >nul & cd /d "%~dp0" & python emulator.py --watch"
timeout /t 2 /nobreak >nul
start "Авто-Демонстрация (Справа)" cmd /k "chcp 65001 >nul & cd /d "%~dp0" & python demo_live.py"
