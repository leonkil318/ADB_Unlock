#!/bin/sh
set -u
cd "$(dirname "$0")"

fail() { echo "ОШИБКА: $*"; exit 1; }

command -v adb >/dev/null || fail "adb не найден"
[ -f unlock-hu.sh ] || fail "unlock-hu.sh рядом со скриптом не найден"

if [ -z "${ANDROID_SERIAL:-}" ]; then
    n=$(adb devices | tail -n +2 | grep -cw device || true)
    [ "$n" = 1 ] || fail "устройств в 'adb devices': $n. Укажите: ANDROID_SERIAL=<серийник> $0"
    ANDROID_SERIAL=$(adb devices | tail -n +2 | grep -w device | head -1 | awk '{print $1}')
    export ANDROID_SERIAL
fi
echo "Машина: $ANDROID_SERIAL"

booted() {
    t=0
    while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != 1 ]; do
        sleep 3
        t=$((t + 3))
        [ $t -lt 300 ] || return 1
    done
}

ready() {
    adb wait-for-device
    booted
    b=$?
    adb root >/dev/null 2>&1
    sleep 2
    adb wait-for-device
    return $b
}

i=0
while [ $i -lt 8 ]; do
    i=$((i + 1))
    mode=
    if ! ready; then
        mode=rescue
        echo "ГУ не загрузилось за 5 минут — проверяю слой прежней прошивки..."
    fi
    adb push unlock-hu.sh /data/local/tmp/gt-unlock.sh >/dev/null 2>&1 || fail "скрипт не скопирован на ГУ"
    out=$(adb shell sh /data/local/tmp/gt-unlock.sh $mode | tr -d '\r')
    echo "$out" | grep -v '^GT:'
    case "$(echo "$out" | grep '^GT:' | tail -1)" in
        GT:OK)
            adb shell rm -f /data/local/tmp/gt-unlock.sh
            echo "Готово: установка приложений не заблокирована."
            exit 0
            ;;
        GT:REMOUNT)
            adb remount >/dev/null 2>&1
            ;;
        GT:REBOOT)
            echo "Перезагружаю ГУ, это около двух минут..."
            adb reboot
            sleep 20
            ;;
        *)
            fail "не получилось. Пришлите весь вывод скрипта."
            ;;
    esac
done
fail "не закончено за $i проходов. Пришлите весь вывод скрипта."
