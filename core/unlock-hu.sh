V=com.ecarx.xsfinstallverifier
P=/product/build.prop
K=ro.vendor.ecarx.app_verify
MARK=/data/local/tmp/gt-unlock.remount

park() {
    root="$1"
    moved=
    for u in "$root"/overlay/*/upper; do
        [ -d "$u" ] || continue
        [ -n "$(ls -A "$u" 2>/dev/null)" ] || continue
        [ -n "$moved" ] || moved="$root/old-$(date +%Y%m%d-%H%M%S)"
        name=$(basename "$(dirname "$u")")
        mkdir -p "$moved/$name"
        for f in "$u"/* "$u"/.[!.]*; do
            [ -e "$f" ] || [ -L "$f" ] || continue
            mv "$f" "$moved/$name/" || return 1
        done
    done
    [ -z "$moved" ] || echo "Слой прежней прошивки отодвинут: ${moved#$root/} (в разделе scratch, не удалён)"
    return 0
}

if [ "$(id -u)" != 0 ]; then
    echo "ОШИБКА: нет root (adb root)"
    echo GT:FAIL
    exit
fi

if [ "$1" = rescue ]; then
    if mount | grep -q ' on /mnt/scratch '; then
        park /mnt/scratch || { echo "ОШИБКА: слой не отодвинут"; echo GT:FAIL; exit; }
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
    echo GT:REBOOT
    exit
fi

if [ -e /dev/block/mapper/scratch ]; then
    M=/data/local/tmp/gt-scratch
    mkdir -p "$M"
    if mount /dev/block/mapper/scratch "$M" 2>/dev/null; then
        park "$M" || { umount "$M"; echo "ОШИБКА: слой не отодвинут"; echo GT:FAIL; exit; }
        umount "$M"
    fi
    rmdir "$M" 2>/dev/null
fi
touch "$MARK"
echo "Проверка подписи Parrot: включена, открываю системные разделы"
echo GT:REMOUNT
