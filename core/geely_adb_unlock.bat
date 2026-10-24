@echo off
setlocal enabledelayedexpansion
title GEELY EX5 EM-i - ADB UNLOCK
color 0A

set "ADB=%~dp0adb.exe"
if not exist "%ADB%" set "ADB=adb"

set "VHAL=/system/bin/lshal debug android.hardware.automotive.vehicle@2.0::IVehicle/default --set 557872680 i 0 a 0"

echo ============================================================
echo   GEELY EX5 EM-i - ADB UNLOCK
echo ============================================================
echo.
echo   1. Put the jumper in, boot the head unit.
echo   2. Start this script NOW and leave it running.
echo   3. Run Factory Reset from the head unit settings menu.
echo.
echo   The script waits for ADB, grabs root, remounts, and sets
echo   USB_SWITCH=0 using the full path to lshal.
echo   Every failed try needs a NEW Factory Reset - the script
echo   just keeps waiting for the next one.
echo   Press CTRL+C to stop.
echo ============================================================
echo.

set /a ATTEMPT=0

:WAIT_DEVICE
"%ADB%" get-state >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto WAIT_DEVICE
)

set /a ATTEMPT+=1
echo [%time%] Device is up. Attempt !ATTEMPT!. Asking for root...

"%ADB%" root >nul 2>&1
"%ADB%" wait-for-device >nul 2>&1
"%ADB%" remount >nul 2>&1

echo [%time%] Sending VHAL command...

set "OUT="
for /f "delims=" %%A in ('"%ADB%" shell %VHAL% 2^>^&1') do set "OUT=!OUT! %%A"

echo         !OUT!

echo !OUT! | findstr /C:"Set property" >nul
if not errorlevel 1 goto DONE

echo !OUT! | findstr /C:"Must be root" >nul
if not errorlevel 1 (
    echo [%time%] Root was lost - the 20s window is over.
    echo [%time%] Run Factory Reset again, script keeps waiting.
)

timeout /t 1 /nobreak >nul
goto WAIT_DEVICE

:DONE
echo.
echo ============================================================
echo [%time%] SUCCESS - ADB is now permanent.
echo ============================================================
echo.
echo Next steps, one by one:
echo.
echo   "%ADB%" root
echo   "%ADB%" remount
echo   "%ADB%" push TESTKEY.x509.pem /system/etc/security/parrot/TESTKEY.x509.pem
echo   "%ADB%" reboot
echo.
echo Then install the helper apk, then disable signature check.
echo Do NOT pull the jumper until a toggle app is installed.
echo.
pause
