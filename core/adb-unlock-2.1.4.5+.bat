@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

where adb >nul 2>&1
if errorlevel 1 (echo ОШИБКА: adb не найден & exit /b 1)
if not exist unlock-hu.sh (echo ОШИБКА: unlock-hu.sh рядом со скриптом не найден & exit /b 1)

if "%ANDROID_SERIAL%"=="" (
    set N=0
    for /f "skip=1 tokens=1,2" %%a in ('adb devices') do if "%%b"=="device" (set /a N+=1 & set ANDROID_SERIAL=%%a)
    if not "!N!"=="1" (
        echo ОШИБКА: устройств в "adb devices": !N!. Укажите нужное: set ANDROID_SERIAL=серийник
        exit /b 1
    )
)
echo Машина: %ANDROID_SERIAL%

set OUT=%TEMP%\gt-unlock.txt
set I=0

:pass
set /a I+=1
if %I% gtr 8 (echo ОШИБКА: не закончено за 8 проходов. Пришлите весь вывод скрипта. & exit /b 1)
set MODE=
adb wait-for-device
set T=0
:boot
set B=
for /f %%b in ('adb shell getprop sys.boot_completed 2^>nul') do set B=%%b
if "%B%"=="1" goto booted
timeout /t 3 /nobreak >nul
set /a T+=3
if %T% lss 300 goto boot
set MODE=rescue
echo ГУ не загрузилось за 5 минут — проверяю слой прежней прошивки...
:booted
adb root >nul 2>&1
timeout /t 2 /nobreak >nul
adb wait-for-device

adb push unlock-hu.sh /data/local/tmp/gt-unlock.sh >nul 2>&1
if errorlevel 1 (echo ОШИБКА: скрипт не скопирован на ГУ & exit /b 1)
adb shell sh /data/local/tmp/gt-unlock.sh %MODE% > "%OUT%"
findstr /v /b "GT:" "%OUT%"
set TOK=
for /f %%t in ('findstr /b "GT:" "%OUT%"') do set TOK=%%t
del "%OUT%" >nul 2>&1

if "%TOK%"=="GT:OK" (
    adb shell rm -f /data/local/tmp/gt-unlock.sh
    echo Готово: установка приложений не заблокирована.
    exit /b 0
)
if "%TOK%"=="GT:REMOUNT" (
    adb remount >nul 2>&1
    goto pass
)
if "%TOK%"=="GT:REBOOT" (
    echo Перезагружаю ГУ, это около двух минут...
    adb reboot
    timeout /t 20 /nobreak >nul
    goto pass
)
echo ОШИБКА: не получилось. Пришлите весь вывод скрипта.
exit /b 1
