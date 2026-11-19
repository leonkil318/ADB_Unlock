@echo off
rem =========================================================
rem Launch 50/50 Split Screen for Manual Testing
rem =========================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Запуск интерактивного стенда Geely...
wt.exe --title "Geely HU Interactive Stand" -d "%~dp0" cmd /k "chcp 65001 >nul & title Эмулятор ГУ (Стенд) & python emulator.py" ^; split-pane -V -d "%~dp0\.." cmd /k "chcp 65001 >nul & title Geely ADB Unlock Master (Справа) & СТАРТ_Windows.bat"
if not errorlevel 1 exit /b 0

rem Fallback if wt.exe is not available: open 2 separate classic windows
start "Эмулятор ГУ (Слева)" cmd /k "chcp 65001 >nul & cd /d "%~dp0" & python emulator.py"
timeout /t 2 /nobreak >nul
start "Geely ADB Unlock Master (Справа)" cmd /k "chcp 65001 >nul & cd /d "%~dp0\.." & СТАРТ_Windows.bat"
