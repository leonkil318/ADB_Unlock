@echo off
rem =========================================================
rem Geely Head Unit (HU) Stand Emulator Launcher
rem =========================================================
chcp 65001 >nul
title Geely HU Stand Emulator
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in system PATH!
    echo Please install Python 3.8+ to run the virtual stand emulator.
    pause
    exit /b 1
)

python emulator.py
if errorlevel 1 pause
