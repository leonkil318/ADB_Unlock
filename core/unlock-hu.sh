#!/system/bin/sh
# Based on supplied unlock-hu.sh; host orchestrators handle bounded retries.
V=com.ecarx.xsfinstallverifier
P=/product/build.prop
K=ro.vendor.ecarx.app_verify
MARK=/data/local/tmp/gt-unlock.remount

park() {
    root="$1"
    moved=
    what=
    for u in "$root"/overlay/*/upper; do
        [ -d "$u" ] || continue
        [ -n "$(ls -A "$u" 2>/dev/null)" ] || continue
        [ -n "$moved" ] || moved="$root/old-$(date +%Y%m%d-%H%M%S)-$$"
        name=$(basename "$(dirname "$u")")
        n=$(find "$u" -mindepth 1 2>/dev/null | wc -l | tr -d " ")
        mkdir -p "$moved/$name" || return 1
        for f in "$u"/* "$u"/.[!.]* "$u"/..?*; do
            [ -e "$f" ] || [ -L "$f" ] || continue
            mv "$f" "$moved/$name/" || return 1
        done
        what="$what $name: $n"
    done
    [ -z "$moved" ] || echo "Слой прежней прошивки отодвинут (${what# }) — ${moved#$root/} в разделе scratch, не удалён"
    return 0
}

scratch() {
    if mount | grep -q ' on /mnt/scratch '; then
        park /mnt/scratch
        return
    fi
    [ -e /dev/block/mapper/scratch ] || return 0
    M=/data/local/tmp/gt-scratch
    mkdir -p "$M" || return 1
    if ! mount /dev/block/mapper/scratch "$M" 2>/dev/null && ! mount -t f2fs /dev/block/mapper/scratch "$M" 2>/dev/null &&
        ! mount -t ext4 /dev/block/mapper/scratch "$M" 2>/dev/null; then
        rmdir "$M" 2>/dev/null
        echo "ОШИБКА: раздел scratch есть, но не открывается — системные разделы не трогаю"
        return 1
    fi
    park "$M"
    r=$?
    umount "$M" || return 1
    rmdir "$M" 2>/dev/null
    return $r
}

fail() { echo "ОШИБКА: $*"; echo GT:FAIL; exit 1; }
[ "$(id -u)" = 0 ] || fail 'нет root (adb root)'

users=$(pm list users 2>/dev/null) || fail 'не удалось получить пользователей ГУ'
users=$(printf '%s\n' "$users" | sed -n 's/.*UserInfo{\([0-9]*\):.*/\1/p')
[ -n "$users" ] || fail 'пустой список пользователей'
property=$(getprop "$K") || fail 'не удалось прочитать app_verify'
case "$property" in true|false|'') ;; *) fail 'неизвестное значение app_verify' ;; esac

check_settings() {
    for setting in package_verifier_enable verifier_verify_adb_installs; do
        [ "$(settings get global "$setting" 2>/dev/null)" = 0 ] || return 1
    done
}

check_packages() {
    for user in $users; do
        packages=$(pm list packages -e --user "$user" 2>/dev/null) || return 1
        if printf '%s\n' "$packages" | grep -qx "package:$V"; then return 1; fi
    done
}

if [ "${1:-}" = verify ]; then
    check_settings || fail 'после перезагрузки настройки проверки установок не равны 0'
    check_packages || fail 'после перезагрузки AutoInstallVerifier включён или его состояние недоступно'
    [ "$property" != true ] || fail 'после перезагрузки app_verify=true'
    echo GT:OK
    exit 0
fi

disabled=
for user in $users; do
    packages=$(pm list packages -e --user "$user" 2>/dev/null) || fail 'не удалось проверить AutoInstallVerifier'
    if printf '%s\n' "$packages" | grep -qx "package:$V"; then
        pm disable-user --user "$user" "$V" || fail "AutoInstallVerifier не выключился для пользователя $user"
        disabled=1
    fi
done
# As in the supplied helper: give the system time before checking it stayed off.
[ -z "$disabled" ] || sleep 15
check_packages || fail 'AutoInstallVerifier не выключился'
echo 'AutoInstallVerifier: нет или выключен для всех пользователей'

for setting in package_verifier_enable verifier_verify_adb_installs; do
    if [ "$(settings get global "$setting" 2>/dev/null)" != 0 ]; then
        settings put global "$setting" 0 || fail "не записана настройка $setting"
    fi
done
check_settings || fail 'не удалось отключить проверки установки в settings'

# After the verifier and settings, as in the supplied helper: those still help here.
if [ -z "$property" ] && [ -d /system/etc/security/parrot ] && getprop ro.build.product | grep -q e245_eu; then
    echo 'На этой прошивке Parrot не имеет поддерживаемого выключателя'
    echo GT:PARROT
    exit 0
fi

if [ "$property" != true ]; then
    rm -f "$MARK"
    echo 'Проверка подписи Parrot: выключена'
    echo GT:OK
    exit 0
fi

# Literal dots: do not match a different property by accident.
if grep -q '^ro\.vendor\.ecarx\.app_verify=false$' "$P" 2>/dev/null; then
    echo GT:REBOOT
    exit 0
fi

# adb remount may yield either overlayfs or a writable physical filesystem.
if mount | grep ' on /product ' | grep -Eq 'overlay|[(,]rw[,)]'; then
    if sed -i 's/^ro\.vendor\.ecarx\.app_verify=true$/ro.vendor.ecarx.app_verify=false/' "$P" &&
        grep -q '^ro\.vendor\.ecarx\.app_verify=false$' "$P"; then
        echo GT:REBOOT
    else
        fail 'не удалось изменить app_verify в /product/build.prop'
    fi
    exit 0
fi

if [ -f "$MARK" ]; then
    scratch || fail 'слой прежней прошивки не отодвинут'
    # Consume this recovery attempt before reboot so a failed/interrupted
    # remount can be requested again on the next pass.
    rm -f "$MARK" || fail 'не удалось удалить маркер remount'
    echo GT:REBOOT
    exit 0
fi

scratch || fail 'слой прежней прошивки не отодвинут'
touch "$MARK" || fail 'не удалось сохранить маркер remount'
echo 'Проверка подписи включена; требуется remount'
echo GT:REMOUNT
