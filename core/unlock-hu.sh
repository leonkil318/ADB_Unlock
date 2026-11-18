#!/system/bin/sh
V=com.ecarx.xsfinstallverifier
P=/product/build.prop
K=ro.vendor.ecarx.app_verify
MARK=/data/local/tmp/gt-unlock.remount
BOOT=/proc/sys/kernel/random/boot_id

park() {
    root="$1"
    moved=
    what=
    for u in "$root"/overlay/*/upper; do
        [ -d "$u" ] || continue
        [ -n "$(ls -A "$u" 2>/dev/null)" ] || continue
        [ -n "$moved" ] || moved="$root/old-$(date +%Y%m%d-%H%M%S)"
        name=$(basename "$(dirname "$u")")
        n=$(find "$u" -mindepth 1 2>/dev/null | wc -l | tr -d " ")
        mkdir -p "$moved/$name"
        for f in "$u"/* "$u"/.[!.]*; do
            [ -e "$f" ] || [ -L "$f" ] || continue
            mv "$f" "$moved/$name/" || return 1
        done
        what="$what $name: $n"
    done
    [ -z "$moved" ] || echo "Слой прежней прошивки отодвинут (${what# }) — ${moved#$root/} в разделе scratch, не удалён"
    [ -z "$moved" ] || echo "Медиамост и нижняя панель GeelyTune, если стояли, ушли вместе со слоем: после загрузки установите их заново — GeelyTune, «Обновление» → «Компоненты»"
    return 0
}

scratch() {
    if mount | grep -q ' on /mnt/scratch '; then
        park /mnt/scratch
        return
    fi
    [ -e /dev/block/mapper/scratch ] || return 0
    M=/data/local/tmp/gt-scratch
    mkdir -p "$M"
    if ! mount /dev/block/mapper/scratch "$M" 2>/dev/null && ! mount -t f2fs /dev/block/mapper/scratch "$M" 2>/dev/null &&
        ! mount -t ext4 /dev/block/mapper/scratch "$M" 2>/dev/null; then
        rmdir "$M" 2>/dev/null
        echo "ОШИБКА: раздел scratch есть, но не открывается — системные разделы не трогаю"
        return 1
    fi
    park "$M"
    r=$?
    umount "$M"
    rmdir "$M" 2>/dev/null
    return $r
}

if [ "$(id -u)" != 0 ]; then
    echo "ОШИБКА: ГУ не дало root (adb root) за минуту. Запустите скрипт ещё раз"
    echo GT:FAIL
    exit
fi

if [ "$1" = rescue ]; then
    if mount | grep -q ' on /mnt/scratch ' || [ -e /dev/block/mapper/scratch ]; then
        scratch || { echo "ОШИБКА: слой не отодвинут"; echo GT:FAIL; exit; }
        echo GT:REBOOT
    else
        echo "ОШИБКА: ГУ не загрузилось, раздела scratch нет"
        echo GT:FAIL
    fi
    exit
fi

if pm list packages -e 2>/dev/null | grep -qx "package:$V"; then
    for u in $(pm list users 2>/dev/null | sed -n 's/.*UserInfo{\([0-9]*\):.*/\1/p'); do
        pm disable-user --user "$u" "$V" >/dev/null 2>&1
    done
    sleep 15
    if pm list packages -e 2>/dev/null | grep -qx "package:$V"; then
        echo "ОШИБКА: проверяющий установок не выключился"
        echo GT:FAIL
        exit
    fi
    echo "Проверяющий установок (AutoInstallVerifier): выключен"
else
    echo "Проверяющий установок (AutoInstallVerifier): нет или уже выключен"
fi

for s in package_verifier_enable verifier_verify_adb_installs; do
    [ "$(settings get global $s 2>/dev/null)" = 0 ] || settings put global $s 0
done

# Свойства нет, а хранилище Parrot есть — ранняя прошивка: проверка включена
# всегда (EX5 EV e245_eu 24.07; EM-i p145_eu, 24.10 — прежде признак был только у EV).
if [ -z "$(getprop $K)" ] && [ -d /system/etc/security/parrot ]; then
    echo "Проверка подписи Parrot: на этой прошивке она включена всегда и выключателя не имеет"
    echo GT:PARROT
    exit
fi

if [ -z "$(getprop $K)" ] && [ "$(getprop ro.boot.veritymode)" != disabled ]; then
    echo "Проверка подписи Parrot: на этой прошивке её нет"
    B=$(cat "$BOOT" 2>/dev/null)
    if [ -f "$MARK" ]; then
        if [ "$(cat "$MARK")" != "$B" ]; then
            rm -f "$MARK"
            echo "Системные разделы не открылись: нижняя панель и системная копия медиамоста на этой прошивке не встанут"
            echo GT:OK
            exit
        fi
        scratch || { echo GT:FAIL; exit; }
        echo "Системные разделы: нужна перезагрузка"
        echo GT:REBOOT
        exit
    fi
    scratch || { echo GT:FAIL; exit; }
    echo "$B" > "$MARK"
    echo "Открываю системные разделы для нижней панели и медиамоста"
    echo GT:REMOUNT
    exit
fi

if [ "$(getprop $K)" != true ]; then
    rm -f "$MARK"
    echo "Проверка подписи Parrot: выключена"
    echo GT:OK
    exit
fi

if grep -q "^$K=false" "$P" 2>/dev/null; then
    echo "Проверка подписи Parrot: выключена в файле, нужна перезагрузка"
    echo GT:REBOOT
    exit
fi

if mount | grep ' on /product ' | grep -q overlay; then
    if sed -i "s/^$K=true\$/$K=false/" "$P" 2>/dev/null && grep -q "^$K=false" "$P"; then
        echo "Проверка подписи Parrot: выключена, нужна перезагрузка"
        echo GT:REBOOT
    else
        echo GT:REMOUNT
    fi
    exit
fi

if [ -f "$MARK" ]; then
    scratch || { echo GT:FAIL; exit; }
    echo GT:REBOOT
    exit
fi

scratch || { echo GT:FAIL; exit; }
touch "$MARK"
echo "Проверка подписи Parrot: включена, открываю системные разделы"
echo GT:REMOUNT
