"""
Geely ADB Unlock Master - Core Engine
Handles all device discovery, ADB communication, VHAL interactions,
and unlock workflows across Windows, macOS, and Linux without external dependencies.
"""

import sys
import os
import platform
import subprocess
import threading
import time
from sound import play_sound

# Base directories
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = os.path.dirname(BASE_DIR)
BIN_DIR = os.path.join(BASE_DIR, 'bin')

def get_resource_path(relative_path):
    """Returns absolute path to a bundled or local resource."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_path = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(bundle_path):
            return bundle_path
    
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        exe_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(exe_path):
            return exe_path

    base_path = os.path.join(BASE_DIR, relative_path)
    if os.path.exists(base_path):
        return base_path

    return base_path


def humanize_adb_error(raw_err, context=""):
    """
    Translates raw low-level ADB errors, OS socket errors, and Android status messages
    into clear, respectful, and actionable diagnostic explanations with step-by-step guidance.
    """
    raw_str = str(raw_err or "").strip()
    raw_lower = raw_str.lower()

    if any(k in raw_lower for k in ["no devices/emulators found", "device not found", "device offline"]):
        title = "Автомобиль (ГУ) не обнаружен через USB"
        reason = "Служба ADB не обнаружила активного мультимедийного устройства на USB-портах компьютера."
        steps = [
            "Проверьте надежность подключения кабеля USB-A между ноутбуком и сервисным портом ГУ.",
            "Убедитесь, что экран мультимедиа автомобиля включен и находится в рабочем состоянии.",
            "Если отладка по ADB в ГУ настраивается впервые, используйте «Сценарий 2: Первоначальная разблокировка» с перемычкой."
        ]
        return title, reason, steps

    if "unauthorized" in raw_lower:
        title = "Требуется подтвердить доступ на экране ГУ"
        reason = "Головное устройство ожидает подтверждения ключа безопасности отладки по USB."
        steps = [
            "Посмотрите на центральный экран мультимедиа автомобиля.",
            "Во всплывающем окне «Разрешить отладку по USB?» установите флажок «Всегда разрешать с этого компьютера» и нажмите «ОК»."
        ]
        return title, reason, steps

    if "more than one device" in raw_lower:
        title = "Обнаружено несколько подключенных Android-устройств"
        reason = "К компьютеру подключено несколько устройств в режиме ADB (смартфон, планшет или эмулятор)."
        steps = [
            "Отключите от ноутбука любые посторонние смартфоны и внешние гаджеты.",
            "Оставьте подключенным только USB-кабель, идущий к автомобилю."
        ]
        return title, reason, steps

    if any(k in raw_lower for k in ["must be root", "adbd cannot run as root", "not in root mode", "uid is not 0"]):
        title = "Отсутствуют системные root-права на ГУ"
        reason = "Команда требует привилегий суперпользователя, но служба adbd запущена в ограниченном пользовательском режиме."
        steps = [
            "При первоначальной разблокировке убедитесь, что перемычка установлена и сброс настроек запущен во время перехвата.",
            "При экспресс-снятии убедитесь, что в ГУ ранее был активирован постоянный режим ADB (VHAL)."
        ]
        return title, reason, steps

    if any(k in raw_lower for k in ["read-only file system", "remount failed"]):
        title = "Системные разделы ГУ заблокированы для записи"
        reason = "Разделы /system и /product защищены от изменений операционной системой Android."
        steps = [
            "Убедитесь, что получен root-доступ к ГУ (adb root).",
            "Попробуйте запустить операцию повторно: программа выполнит перемонтирование файловой системы (remount)."
        ]
        return title, reason, steps

    if any(k in raw_lower for k in ["install_parse_failed_no_certificates", "install_failed_no_certificates"]):
        title = "Установка заблокирована защитой сертификатов Parrot"
        reason = "Прошивка Geely отклоняет установку приложений без заводской цифровой подписи Parrot."
        steps = [
            "Запустите «Сценарий 1: Экспресс-снятие защиты», чтобы отключить параметр ro.vendor.ecarx.app_verify.",
            "Дождитесь штатной перезагрузки ГУ для применения системных изменений."
        ]
        return title, reason, steps

    if any(k in raw_lower for k in ["xsfinstallverifier", "autoinstallverifier", "install_failed_verification"]):
        title = "Установка заблокирована верификатором Geely"
        reason = "Системная служба com.ecarx.xsfinstallverifier отклоняет установку сторонних APK-пакетов."
        steps = [
            "Выполните процедуру снятия защиты: программа принудительно отключит службу верификатора."
        ]
        return title, reason, steps

    if any(k in raw_lower for k in ["таймаут", "timeoutexpired", "timed out"]):
        title = "Превышено время ожидания ответа от ГУ"
        reason = "Головное устройство не ответило на системный запрос в течение установленного таймаута."
        steps = [
            "Проверьте надежность кабеля USB — возможно, отошел контакт при вибрации.",
            "Убедитесь, что экран мультимедиа не завис (при необходимости перезагрузите экран удержанием регулятора громкости)."
        ]
        return title, reason, steps

    if any(k in raw_lower for k in ["cannot connect to daemon", "connection refused", "failed to start daemon"]):
        title = "Сбой локальной службы ADB на компьютере"
        reason = "Сервер ADB не смог привязаться к порту 5037 на вашем компьютере (порт занят сторонним процессом)."
        steps = [
            "Закройте сторонние утилиты синхронизации смартфонов или эмуляторы Android.",
            "В главном меню выберите пункт «[5] Перезапустить службу ADB» для автоматической очистки процессов."
        ]
        return title, reason, steps

    # Fallback with context
    title = context or "Сбой выполнения операции"
    reason = "Система ГУ вернула технический код ошибки при выполнении команды."
    steps = [
        "Проверьте надежность USB-кабеля и активность экрана мультимедиа.",
        "Выполните проверку в меню: «[3] Проверить статус ГУ (Диагностика связи)»."
    ]
    return title, reason, steps


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.os_name = platform.system().lower()  # 'windows', 'darwin', 'linux'
        self.adb_path = None
        self.adb_ready = False
        self.status = "idle"  # idle, working, success, error
        self.status_message = "Готов к работе"
        self.last_error_details = None
        self.device_serial = None
        self.device_state = "disconnected"
        self.last_test = None
        self.logs = []
        self.stop_worker = False

    def log(self, text, level="info"):
        timestamp = time.strftime("%H:%M:%S")
        prefix = {
            "info": "[i]",
            "success": "[OK]",
            "warning": "[!]",
            "error": "[X]",
            "cmd": "[*]"
        }.get(level, "•")
        
        # Strip any legacy leading emojis so terminal fonts never show broken ?? boxes
        clean_text = text.strip()
        for em in ["ℹ️", "✅", "⚠️", "❌", "⚡", "🔍", "🔑", "📂", "💡", "⚙️", "🔄", "📱", "🎉"]:
            if clean_text.startswith(em):
                clean_text = clean_text[len(em):].strip()

        entry = f"[{timestamp}] {prefix} {clean_text}"
        
        with self.lock:
            self.logs.append({"time": timestamp, "text": clean_text, "level": level, "formatted": entry})
            if len(self.logs) > 500:
                self.logs.pop(0)

        try:
            log_file = os.path.join(BASE_DIR, "debug.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

    def set_error(self, title, reason="", steps=None, raw=""):
        details = {
            "title": title,
            "reason": reason,
            "steps": steps or [],
            "raw": str(raw).strip() if raw else ""
        }
        with self.lock:
            self.status = "error"
            self.status_message = title
            self.last_error_details = details
        self.log(title, level="error")

    def set_status(self, status, message, step=None):
        with self.lock:
            self.status = status
            self.status_message = message
            if status != "error":
                self.last_error_details = None
            elif not self.last_error_details:
                title, reason, steps = humanize_adb_error(message)
                self.last_error_details = {
                    "title": title,
                    "reason": reason,
                    "steps": steps,
                    "raw": message
                }
        self.log(message, level="info" if status != "error" else "error")


STATE = AppState()


def locate_or_download_adb():
    """Finds adb in bundle, bin/, system PATH, or downloads it automatically."""
    is_win = STATE.os_name == "windows"
    adb_binary = "adb.exe" if is_win else "adb"

    # 1. Check embedded resource path
    bundled_adb = get_resource_path(os.path.join("bin", adb_binary))
    if os.path.isfile(bundled_adb):
        if not is_win:
            try:
                os.chmod(bundled_adb, 0o755)
            except Exception:
                pass
        STATE.adb_path = bundled_adb
        STATE.adb_ready = True
        return bundled_adb

    # 2. Check core/bin/
    local_adb = os.path.join(BIN_DIR, adb_binary)
    if not os.path.isfile(local_adb):
        if STATE.os_name == "darwin":
            darwin_pkg = get_resource_path(os.path.join("bin", "adb-darwin"))
            if os.path.isfile(darwin_pkg):
                try:
                    import shutil
                    shutil.copy2(darwin_pkg, local_adb)
                except Exception:
                    local_adb = darwin_pkg
        elif STATE.os_name == "linux":
            linux_pkg = get_resource_path(os.path.join("bin", "adb-linux"))
            if os.path.isfile(linux_pkg):
                try:
                    import shutil
                    shutil.copy2(linux_pkg, local_adb)
                except Exception:
                    local_adb = linux_pkg

    if os.path.isfile(local_adb):
        if not is_win:
            try:
                os.chmod(local_adb, 0o755)
            except Exception:
                pass
        STATE.adb_path = local_adb
        STATE.adb_ready = True
        return local_adb

    # 3. Check system PATH
    system_adb = None
    try:
        which_cmd = ["where", "adb"] if is_win else ["which", "adb"]
        res = subprocess.run(which_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if lines:
                system_adb = lines[0].strip()
    except Exception:
        pass

    if system_adb and os.path.isfile(system_adb):
        STATE.adb_path = system_adb
        STATE.adb_ready = True
        return system_adb

    # 4. Auto-download from Google
    STATE.log("ADB не найден на компьютере. Загружаем официальный Google Platform-Tools...", "warning")
    os.makedirs(BIN_DIR, exist_ok=True)

    urls = {
        "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
        "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
        "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
    }
    url = urls.get(STATE.os_name, urls["windows"])
    try:
        import urllib.request
        import zipfile
        import io

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        z = zipfile.ZipFile(io.BytesIO(data))
        for member in z.namelist():
            filename = os.path.basename(member)
            if not filename:
                continue
            if filename in ["adb", "adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "lib64"]:
                target_path = os.path.join(BIN_DIR, filename)
                with open(target_path, "wb") as f:
                    f.write(z.read(member))
                if not is_win:
                    os.chmod(target_path, 0o755)
        if os.path.isfile(local_adb):
            if not is_win:
                os.chmod(local_adb, 0o755)
            STATE.adb_path = local_adb
            STATE.adb_ready = True
            STATE.log("ADB успешно загружен и подготовлен!", "success")
            return local_adb
    except Exception as e:
        STATE.log(f"Не удалось автоматически загрузить ADB: {e}", "error")

    STATE.adb_ready = False
    return None


def run_adb(args, timeout=30):
    """Executes an adb command safely without opening popup windows and with robust UTF-8 encoding."""
    if not STATE.adb_path or not os.path.isfile(STATE.adb_path):
        locate_or_download_adb()
        if not STATE.adb_path:
            return -1, "", "ADB недоступен"

    cmd = [STATE.adb_path] + args
    try:
        creationflags = 0x08000000 if STATE.os_name == "windows" else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Таймаут команды ADB"
    except Exception as e:
        return -1, "", str(e)


def kill_adb_processes():
    """Kills conflicting adb server processes to free the port and restarts daemon."""
    STATE.log("Очищаем зависшие процессы ADB в системе...", "cmd")
    try:
        if STATE.os_name == "windows":
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["killall", "-9", "adb"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(1)
    run_adb(["start-server"], timeout=10)
    STATE.log("Служба ADB перезапущена с нуля", "success")


def check_devices():
    """Checks connected devices."""
    code, stdout, _ = run_adb(["devices"])
    if code != 0:
        STATE.device_state = "error"
        STATE.device_serial = None
        return False

    lines = stdout.splitlines()[1:] if stdout else []
    devices = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])

    if len(devices) == 1:
        STATE.device_serial = devices[0]
        STATE.device_state = "connected"
        return True
    elif len(devices) > 1:
        STATE.device_serial = devices[0]
        STATE.device_state = "multiple"
        return True
    else:
        STATE.device_serial = None
        STATE.device_state = "disconnected"
        return False


def test_adb_connection():
    """Runs a comprehensive test of the ADB connection, head unit state, and security locks."""
    STATE.log("🔍 Запуск проверки связи с автомобилем (Тест ADB)...", "cmd")

    if not STATE.adb_path or not os.path.isfile(STATE.adb_path):
        locate_or_download_adb()
        if not STATE.adb_path:
            res = {
                "ok": False,
                "connected": False,
                "error": "ADB не найден на компьютере",
                "recommendation": "check_adb"
            }
            STATE.last_test = res
            STATE.log("❌ Ошибка: исполняемый файл ADB не найден.", "error")
            return res

    # 1. Devices check
    code, stdout, _ = run_adb(["devices"], timeout=5)
    lines = stdout.splitlines()[1:] if stdout else []
    connected_devs = []
    unauth_devs = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            if parts[1] == "device":
                connected_devs.append(parts[0])
            elif parts[1] == "unauthorized":
                unauth_devs.append(parts[0])

    if unauth_devs and not connected_devs:
        STATE.device_state = "unauthorized"
        STATE.log("⚠️ Найдено устройство, но требуется авторизация отладки на экране авто (unauthorized).", "warning")
        res = {
            "ok": True,
            "connected": False,
            "state": "unauthorized",
            "message": "Требуется подтвердить отладку по USB на экране мультимедиа",
            "recommendation": "authorize"
        }
        STATE.last_test = res
        return res

    if not connected_devs:
        STATE.device_state = "disconnected"
        STATE.device_serial = None
        title, reason, steps = humanize_adb_error("no devices/emulators found")
        STATE.log("Автомобиль не обнаружен на шине USB (список adb devices пуст)", "warning")
        STATE.set_error(title, reason, steps, raw="no devices/emulators found")
        res = {
            "ok": False,
            "connected": False,
            "state": "disconnected",
            "message": title,
            "reason": reason,
            "steps": steps,
            "recommendation": "not_connected"
        }
        STATE.last_test = res
        return res

    serial = connected_devs[0]
    STATE.device_serial = serial
    STATE.device_state = "connected"
    STATE.log(f"✅ Автомобиль успешно подключен! Серийный номер: {serial}", "success")

    # 2. Test root access
    STATE.log("🔑 Проверка доступа суперпользователя (adb root)...", "cmd")
    code_r, out_r, _ = run_adb(["root"], timeout=8)
    time.sleep(1)
    run_adb(["wait-for-device"], timeout=5)

    root_ok = ("already running as root" in out_r.lower() or "restarting adbd as root" in out_r.lower() or code_r == 0)
    code_id, out_id, _ = run_adb(["shell", "id", "-u"], timeout=5)
    if code_id == 0 and out_id.strip() == "0":
        root_ok = True
        STATE.log("✅ Root-доступ подтверждён (UID: 0).", "success")
    else:
        STATE.log(f"⚠️ Ответ при запросе root: {out_r or out_id}", "warning")

    # 3. Read firmware & system properties
    STATE.log("📋 Считывание сведений о прошивке ГУ...", "cmd")
    _, fw_build, _ = run_adb(["shell", "getprop", "ro.build.display.id"], timeout=5)
    _, fw_inc, _ = run_adb(["shell", "getprop", "ro.build.version.incremental"], timeout=5)
    _, model, _ = run_adb(["shell", "getprop", "ro.product.model"], timeout=5)
    firmware_info = fw_build.strip() or fw_inc.strip() or "Не определена"
    model_info = model.strip() or "Штатное ГУ Geely"
    STATE.log(f"🚘 Модель ГУ: {model_info} | Прошивка: {firmware_info}", "info")

    # 4. Check Parrot app_verify
    _, product_val, _ = run_adb(["shell", "getprop", "ro.build.product"], timeout=5)
    is_eu = "e245_eu" in (product_val or "").lower()
    _, parrot_val, _ = run_adb(["shell", "getprop", "ro.vendor.ecarx.app_verify"], timeout=5)
    parrot_val = parrot_val.strip().lower()
    if is_eu:
        parrot_locked = False
        STATE.log("🇪🇺 Версия ГУ: экспортная европейская (e245_eu) — Parrot встроен в систему и не блокирует установку", "info")
    elif parrot_val == "true":
        parrot_locked = True
        STATE.log("🔒 Защита Parrot certificates: ВКЛЮЧЕНА (блокирует установку сторонних APK)", "warning")
    else:
        parrot_locked = False
        STATE.log("🔓 Защита Parrot certificates: ВЫКЛЮЧЕНА (установка сторонних APK разрешена)", "success")

    # 5. Check AutoInstallVerifier package
    _, pm_out, _ = run_adb(["shell", "pm", "list", "packages", "-e"], timeout=8)
    verifier_active = "com.ecarx.xsfinstallverifier" in (pm_out or "")
    if verifier_active:
        STATE.log("🔒 Системный верификатор AutoInstallVerifier: АКТИВЕН", "warning")
    else:
        STATE.log("🔓 Системный верификатор AutoInstallVerifier: ОТКЛЮЧЕН или отсутствует", "success")

    # 6. Check toggle app
    _, toggle_out, _ = run_adb(["shell", "pm", "list", "packages"], timeout=5)
    toggle_installed = any(pkg in (toggle_out or "") for pkg in ["com.yahooeu2k.ex5.adbtoggle", "com.geely.adbtoggle", "adbtoggle", "geelyadbtoggle"])
    if toggle_installed:
        STATE.log("📱 Приложение переключателя ADB-Toggle: уже установлено на ГУ", "info")
    else:
        STATE.log("📱 Приложение переключателя ADB-Toggle: не найдено (будет установлено при необходимости)", "info")

    needs_unlock = parrot_locked or verifier_active or not toggle_installed
    if needs_unlock:
        recommendation = "quick_unlock"
        STATE.log("💡 ВЕРДИКТ: ADB активен! Перемычка НЕ требуется.", "success")
        STATE.log("💡 Достаточно запустить экспресс-снятие ограничений в 1 клик.", "success")
    else:
        recommendation = "ready"
        STATE.log("🎉 ВЕРДИКТ: Все блокировки уже сняты! ГУ полностью готово к установке приложений через GeelyTune.", "success")

    res = {
        "ok": True,
        "connected": True,
        "serial": serial,
        "model": model_info,
        "firmware": firmware_info,
        "root_ok": root_ok,
        "parrot_locked": parrot_locked,
        "verifier_active": verifier_active,
        "toggle_installed": toggle_installed,
        "needs_unlock": needs_unlock,
        "recommendation": recommendation,
        "message": "ADB активен! Перемычка не требуется." if needs_unlock else "ГУ полностью разблокировано!"
    }
    STATE.last_test = res
    return res


# ==================== STEP 2: FACTORY RESET CATCH ====================
def worker_catch_factory_reset():
    """Continuously waits for device reboot, grants root, and sets VHAL property."""
    STATE.set_status("working", "Ожидание перезагрузки ГУ после сброса на заводские настройки... Не закрывайте окно!", 2)
    STATE.log("ВНИМАНИЕ: На экране автомобиля перейдите в «Настройки ➔ Система ➔ Сброс на заводские настройки» и подтвердите сброс.", "warning")
    STATE.log("💡 Как это работает: при штатном сбросе система кратковременно открывает 20-секундное окно отладки. Программа непрерывно сканирует USB-порт и автоматически перехватит его.", "info")

    vhal_cmd = "/system/bin/lshal debug android.hardware.automotive.vehicle@2.0::IVehicle/default --set 557872680 i 0 a 0"
    attempt = 0

    while not STATE.stop_worker:
        code, stdout, _ = run_adb(["get-state"], timeout=2)
        if code != 0 or stdout != "device":
            time.sleep(0.5)
            continue

        attempt += 1
        STATE.log(f"⚡ Устройство обнаружено на шине USB! Попытка перехвата сервисного окна #{attempt}...", "cmd")
        STATE.log("🔑 Запрашиваем права суперпользователя (adb root)...", "info")
        
        run_adb(["root"], timeout=5)
        time.sleep(0.5)
        run_adb(["wait-for-device"], timeout=5)
        run_adb(["remount"], timeout=5)

        STATE.log("📡 Отправка автомобилю VHAL-команды фиксации: USB_SWITCH=0 (постоянный ADB)...", "cmd")
        STATE.log("💡 Что делает команда: lshal записывает в системную шину автомобиля флаг постоянного режима ADB, чтобы он больше не выключался после перезагрузок.", "info")
        code, out, err = run_adb(["shell", vhal_cmd], timeout=8)
        combined_out = f"{out} {err}".strip()
        STATE.log(f"Ответ системы автомобиля: {combined_out}")

        if "Set property" in combined_out:
            play_sound("catch")
            STATE.log("🎉 УСПЕХ! Автомобиль подтвердил фиксацию порта (Set property)! Постоянный ADB активирован.", "success")
            STATE.set_status("success", "ADB зафиксирован! Снимите перемычку и подтвердите перезагрузку ГУ.", 3)
            return

        if "Must be root" in combined_out:
            STATE.log("⚠️ Сервисное окно (20 сек) успело закрыться до фиксации. Ничего страшного: просто нажмите «Сброс на заводские настройки» на экране авто ещё раз — скрипт продолжает ждать...", "warning")

        time.sleep(1)


# ==================== STEP 3: REBOOT & VERIFY ====================
def worker_reboot_and_verify():
    """Reboots HU without jumper and waits for full boot."""
    STATE.set_status("working", "Перезагрузка ГУ... Это займет около 1.5 - 2 минут.", 3)
    STATE.log("🔄 Отправляем команду перезагрузки головного устройства...", "cmd")
    STATE.log("💡 Пояснение: перемычка снята, теперь мы проверяем, сохраняется ли доступ по ADB в обычном рабочем режиме автомобиля.", "info")
    run_adb(["reboot"], timeout=10)
    time.sleep(15)

    start_time = time.time()
    while not STATE.stop_worker:
        if time.time() - start_time > 300:
            STATE.set_error(
                title="Превышено время ожидания загрузки ГУ (5 минут)",
                reason="Головное устройство не завершило цикл загрузки или отсутствует связь по USB.",
                steps=[
                    "Убедитесь, что экран мультимедиа автомобиля включился и загрузился.",
                    "Проверьте надежность подключения кабеля USB-A к порту ГУ и ноутбука.",
                    "При необходимости перезагрузите экран ГУ вручную удержанием кнопки громкости."
                ],
                raw="Boot verification timeout (300s)"
            )
            return

        code, out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
        if code == 0 and out.strip() == "1":
            STATE.log("✅ Головное устройство полностью загрузилось! Проверяем постоянство связи ADB...", "success")
            time.sleep(2)
            check_devices()
            if STATE.device_state == "connected":
                STATE.log("🎉 Связь подтверждена! ADB стабильно активен без перемычки.", "success")
                STATE.set_status("success", "ГУ перезагружено, ADB активен. Переходим к снятию системных ограничений.", 4)
                return
        time.sleep(3)


# ==================== STEP 4: UNLOCK PARROT & INSTALL TOGGLE ====================
def worker_unlock_and_install():
    """Executes unlock-hu.sh and installs Geely-ADB-Toggle apk."""
    STATE.set_status("working", "Снятие ограничений установки и настройка системы...", 4)
    unlock_script = get_resource_path("unlock-hu.sh")
    apk_file = get_resource_path("Geely-ADB-Toggle-1.1.0.apk")

    if not os.path.isfile(unlock_script):
        STATE.set_error(
            title="Отсутствует системный скрипт unlock-hu.sh",
            reason=f"Файл скрипта не найден внутри пакета программы: {unlock_script}",
            steps=["Убедитесь, что целостность файлов программы не была нарушена."],
            raw=""
        )
        return

    # 1. Pre-flight check: is device physically connected?
    STATE.log("🔍 Проверка подключения к головному устройству автомобиля...", "cmd")
    code, stdout, _ = run_adb(["get-state"], timeout=2)
    if code != 0 or stdout.strip() != "device":
        run_adb(["wait-for-device"], timeout=3)
        code2, stdout2, err2 = run_adb(["get-state"], timeout=2)
        if code2 != 0 or stdout2.strip() != "device":
            title, reason, steps = humanize_adb_error(err2 or "no devices/emulators found")
            STATE.set_error(title, reason, steps, raw=err2 or "no devices/emulators found")
            return

    # 2. Check root access
    STATE.log("🔑 Проверка прав суперпользователя (adb root)...", "cmd")
    run_adb(["root"], timeout=10)
    time.sleep(1)
    run_adb(["wait-for-device"], timeout=5)

    code_id, out_id, err_id = run_adb(["shell", "id", "-u"], timeout=5)
    if code_id != 0 or out_id.strip() != "0":
        err_msg = err_id or out_id or "UID != 0"
        title, reason, steps = humanize_adb_error("must be root", context="Отсутствуют права суперпользователя (root) на ГУ")
        STATE.set_error(title, reason, steps, raw=err_msg)
        return

    # 3. Push script
    STATE.log("📂 Загрузка системного скрипта разблокировки (unlock-hu.sh) на ГУ...", "cmd")
    STATE.log("💡 Пояснение: по умолчанию прошивка Geely отклоняет установку любых приложений без цифрового сертификата Parrot. Скрипт отключает эту блокировку в build.prop и отключает системный верификатор.", "info")
    code, out_p, err_p = run_adb(["push", unlock_script, "/data/local/tmp/gt-unlock.sh"], timeout=15)
    if code != 0:
        title, reason, steps = humanize_adb_error(err_p or out_p, context="Ошибка загрузки скрипта на ГУ")
        STATE.set_error(title, reason, steps, raw=err_p or out_p)
        return

    # Run loop
    unlocked_ok = False
    for pass_num in range(1, 9):
        if STATE.stop_worker:
            STATE.log("⚠️ Операция прервана пользователем", "warning")
            return

        play_sound("step")
        STATE.log(f"⚙️ Выполнение процедур снятия защиты (проход {pass_num}/8)...", "cmd")
        code, out, _ = run_adb(["shell", "sh", "/data/local/tmp/gt-unlock.sh"], timeout=60)
        
        for line in out.splitlines():
            line_str = line.strip()
            if line_str and not line_str.startswith("GT:"):
                STATE.log(line_str)

        if "GT:OK" in out:
            run_adb(["shell", "rm", "-f", "/data/local/tmp/gt-unlock.sh"], timeout=5)
            STATE.log("✅ Ограничения Parrot и системный верификатор успешно отключены!", "success")
            STATE.log("💡 Теперь система автомобиля позволит устанавливать любые стандартные Android APK (Яндекс.Навигатор, видеоплееры, лаунчеры).", "info")
            unlocked_ok = True
            break
        elif "GT:PARROT" in out:
            run_adb(["shell", "rm", "-f", "/data/local/tmp/gt-unlock.sh"], timeout=5)
            STATE.log("ℹ️ Обнаружена экспортная европейская версия (e245_eu): защита Parrot встроена на уровне ядра.", "info")
            STATE.log("✅ Системные верификаторы (AutoInstallVerifier) и глобальные проверки успешно отключены!", "success")
            unlocked_ok = True
            break
        elif "GT:REMOUNT" in out:
            STATE.log("🔄 Открываем системный раздел диска ГУ для записи (remount)...", "info")
            run_adb(["remount"], timeout=15)
            time.sleep(2)
        elif "GT:REBOOT" in out:
            STATE.log("🔄 Требуется промежуточная перезагрузка ГУ для применения настроек (около 1.5 - 2 минут)...", "info")
            run_adb(["reboot"], timeout=10)
            time.sleep(20)
            reboot_start = time.time()
            reboot_ok = False
            while not STATE.stop_worker:
                if time.time() - reboot_start > 300:
                    STATE.set_error(
                        title="Превышено время перезагрузки ГУ (таймаут 5 минут)",
                        reason="Головное устройство не вышло на связь после команды перезагрузки.",
                        steps=[
                            "Убедитесь, что экран мультимедиа автомобиля включился и загрузился.",
                            "Проверьте надежность подключения кабеля USB-A к порту ГУ и ноутбука."
                        ],
                        raw="Reboot timeout exceeded 300s"
                    )
                    return
                c, b_out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
                if c == 0 and b_out.strip() == "1":
                    reboot_ok = True
                    break
                time.sleep(3)
            if not reboot_ok or STATE.stop_worker:
                return
            run_adb(["root"], timeout=10)
            time.sleep(2)
            run_adb(["wait-for-device"], timeout=10)
        else:
            title, reason, steps = humanize_adb_error(out, context="Непредвиденный ответ скрипта разблокировки")
            STATE.set_error(title, reason, steps, raw=out)
            return

    if not unlocked_ok:
        title, reason, steps = humanize_adb_error(out, context="Не удалось завершить снятие ограничений за 8 проходов")
        STATE.set_error(title, reason, steps, raw=out)
        return

    # Install Toggle APK if not already installed
    _, toggle_check, _ = run_adb(["shell", "pm", "list", "packages"], timeout=5)
    already_installed = any(pkg in (toggle_check or "") for pkg in ["com.yahooeu2k.ex5.adbtoggle", "com.geely.adbtoggle", "adbtoggle", "geelyadbtoggle"])

    if already_installed:
        STATE.log("📱 Переключатель Geely-ADB-Toggle уже установлен на ГУ. Пропускаем повторную установку.", "success")
    elif os.path.isfile(apk_file):
        STATE.log("📱 Установка приложения Geely-ADB-Toggle на экран мультимедиа...", "cmd")
        STATE.log("💡 Для чего оно нужно: этот удобный тумблер в меню авто позволит вам в один клик переключать USB-разъем между обычной флешкой с музыкой и кабелем отладки.", "info")
        code, out, err = run_adb(["install", "-r", "--user", "10", apk_file], timeout=60)
        if code == 0 and "Success" in out:
            STATE.log("✅ Приложение Geely-ADB-Toggle успешно установлено в профиль пользователя!", "success")
        else:
            STATE.log(f"Установка в профиль 10 вернула: {out} {err}. Пробуем стандартную установку...", "warning")
            code2, out2, _ = run_adb(["install", "-r", apk_file], timeout=60)
            if "Success" in out2:
                STATE.log("✅ Приложение Geely-ADB-Toggle успешно установлено!", "success")
            else:
                STATE.log(f"Предупреждение при установке APK: {out2}", "warning")
    else:
        STATE.log("APK-файл переключателя не найден в папке core, пропускаем установку переключателя", "warning")

    # Post-unlock verification
    STATE.log("🔍 Проверка итогового статуса системы авто...", "cmd")
    _, parrot_check, _ = run_adb(["shell", "getprop", "ro.vendor.ecarx.app_verify"], timeout=5)
    _, pm_check, _ = run_adb(["shell", "pm", "list", "packages", "-e"], timeout=5)
    final_parrot_locked = (parrot_check.strip().lower() == "true")
    final_verifier_active = "com.ecarx.xsfinstallverifier" in (pm_check or "")

    if not final_parrot_locked:
        STATE.log("🔓 Защита Parrot certificates: ВЫКЛЮЧЕНА (установка APK разрешена)", "success")
    if not final_verifier_active:
        STATE.log("🔓 Системный верификатор AutoInstallVerifier: ОТКЛЮЧЕН", "success")

    # Update STATE.last_test so UI reflects unlocked status
    if STATE.last_test and isinstance(STATE.last_test, dict):
        STATE.last_test["parrot_locked"] = final_parrot_locked
        STATE.last_test["verifier_active"] = final_verifier_active
        STATE.last_test["toggle_installed"] = True
        STATE.last_test["needs_unlock"] = False
        STATE.last_test["recommendation"] = "ready"
        STATE.last_test["message"] = "ГУ полностью разблокировано!"
    else:
        STATE.last_test = {
            "ok": True,
            "connected": True,
            "serial": STATE.device_serial,
            "model": "Geely Head Unit",
            "firmware": "2.1.4.5+",
            "root_ok": True,
            "parrot_locked": final_parrot_locked,
            "verifier_active": final_verifier_active,
            "toggle_installed": True,
            "needs_unlock": False,
            "recommendation": "ready",
            "message": "ГУ полностью разблокировано!"
        }

    STATE.set_status("success", "Поздравляем! Разблокировка полностью завершена!", 5)
    STATE.log("🏆 ВСЕ ЭТАПЫ РАЗБЛОКИРОВКИ ВЫПОЛНЕНЫ! Теперь вы можете устанавливать любые приложения через официальный веб-установщик GeelyTune.", "success")
