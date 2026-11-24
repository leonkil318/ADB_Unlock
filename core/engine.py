"""
Geely ADB Unlock Master - Core Engine
Handles all device discovery, ADB communication, VHAL interactions,
and unlock workflows across Windows, macOS, and Linux without external dependencies.
"""

import sys
import os
import json
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
    into clear, respectful, and actionable diagnostic explanations in plain Russian
    with step-by-step guidance for non-IT users.
    """
    raw_str = str(raw_err or "").strip()
    raw_lower = raw_str.lower()

    # 1. Connection / Device not found / Power sleep / Feature set failure
    if any(k in raw_lower for k in [
        "no devices/emulators found", "no devices", "device not found",
        "failed to get feature set", "device 'null' not found", "error: closed",
        "device offline"
    ]):
        title = "Автомобиль (ГУ) не обнаружен через USB"
        reason = "Компьютер не видит мультимедийную систему автомобиля. Кабель не подключен, автомобиль «уснул» (отключилось питание) либо порт ADB ещё не был активирован."
        steps = [
            "Проверьте USB-кабель: он должен быть надежно и плотно вставлен в порт автомобиля и ноутбука (без переходников и USB-хабов).",
            "Включите питание автомобиля: кратковременно нажмите на педаль тормоза, чтобы экран мультимедиа загорелся и блоки проснулись.",
            "Если отладка по ADB настраивается впервые: сначала выберите в главном меню пункт [2] (Открыть ADB с нуля через перемычку). На закрытом с завода ГУ компьютер не сможет увидеть машину до сброса настроек."
        ]
        return title, reason, steps

    # 2. Unauthorized
    if "unauthorized" in raw_lower:
        title = "Требуется подтвердить доступ на экране ГУ"
        reason = "Головное устройство ожидает вашего подтверждения для связи по USB."
        steps = [
            "Посмотрите на центральный экран мультимедиа автомобиля.",
            "Во всплывающем окне «Разрешить отладку по USB?» установите флажок «Всегда разрешать с этого компьютера» и нажмите «ОК»."
        ]
        return title, reason, steps

    # 3. Multiple devices
    if "more than one device" in raw_lower:
        title = "Подключено несколько USB-устройств"
        reason = "К компьютеру подключено несколько устройств в режиме Android (например, ваш смартфон и кабель автомобиля)."
        steps = [
            "Отключите от ноутбука любые посторонние смартфоны, планшеты и внешние гаджеты.",
            "Оставьте подключенным только USB-кабель, идущий к автомобилю."
        ]
        return title, reason, steps

    # 4. Root / Permissions
    if any(k in raw_lower for k in ["must be root", "adbd cannot run as root", "not in root mode", "uid is not 0", "uid != 0"]):
        title = "Отсутствуют права суперпользователя (root)"
        reason = "Система ГУ не предоставила права доступа к системным разделам."
        steps = [
            "Если вы открываете ADB с нуля: убедитесь, что перемычка установлена в разъём, а сброс настроек запущен при работающей программе.",
            "Если у вас прошивка 2.2.0: запустите Пункт [1] меню (он автоматически применит режим root для GeelyTune)."
        ]
        return title, reason, steps

    # 5. Read-only filesystem / Remount failed / Permission denied
    if any(k in raw_lower for k in [
        "read-only file system", "remount failed", "read-only", "cannot copy",
        "permission denied", "operation not permitted"
    ]):
        title = "Системный раздел ГУ защищен от записи"
        reason = "Заводская система защиты автомобиля блокирует сохранение файлов в системную память ГУ."
        steps = [
            "Убедитесь, что экран автомобиля включен (кратковременно нажмите педаль тормоза при необходимости).",
            "В главном меню выберите пункт [6] (Перезапустить службу ADB), а затем повторите операцию."
        ]
        return title, reason, steps

    # 6. Parrot certificate rejection
    if any(k in raw_lower for k in [
        "install_parse_failed_no_certificates", "install_failed_no_certificates",
        "no certificates", "parrot certificates"
    ]):
        title = "Установка заблокирована защитой Parrot"
        reason = "Заводская прошивка Geely отклонила установку APK, так как в нём нет цифровой подписи завода."
        steps = [
            "Если у вас прошивка 2.1.4.5+ или 2.2.0: выберите Пункт [1] меню (он снимет проверку Parrot и позволит ставить любые программы).",
            "Если у вас ранняя прошивка (до 2.1.4.5): воспользуйтесь пунктом [T] для добавления ключа приложения в хранилище Parrot Trust."
        ]
        return title, reason, steps

    # 7. Verification failure (AutoInstallVerifier)
    is_verifier_turned_off = any(neg in raw_lower for neg in [
        "выключен", "отключен", "disabled", "не найден", "отсутствует", "already disabled"
    ])
    if not is_verifier_turned_off and any(k in raw_lower for k in [
        "install_failed_verification_failure", "install_failed_verifier",
        "autoinstallverifier", "xsfinstallverifier"
    ]):
        title = "Установка заблокирована верификатором Geely"
        reason = "Встроенный робот безопасности ГУ (AutoInstallVerifier) блокирует установку сторонних программ."
        steps = [
            "Запустите Пункт [1] главного меню: программа автоматически отключит системного верификатора для всех профилей."
        ]
        return title, reason, steps

    # 8. Insufficient storage
    if any(k in raw_lower for k in ["install_failed_insufficient_storage", "no space left"]):
        title = "Недостаточно свободной памяти на ГУ"
        reason = "В мультимедийной системе автомобиля закончилось свободное дисковое пространство."
        steps = [
            "Откройте на экране автомобиля настройки и удалите неиспользуемые приложения или загруженную музыку.",
            "Повторите установку приложения."
        ]
        return title, reason, steps

    # 9. App already exists with different signature
    if any(k in raw_lower for k in ["install_failed_update_incompatible", "signatures do not match"]):
        title = "Конфликт подписи ранее установленного приложения"
        reason = "На автомобиле уже установлена другая версия этого приложения с отличной цифровой подписью."
        steps = [
            "Удалите старую версию приложения с экрана автомобиля.",
            "Повторите установку заново."
        ]
        return title, reason, steps

    # 10. Connection broken / Timeout / USB glitch
    if any(k in raw_lower for k in [
        "timeoutexpired", "timed out", "таймаут", "protocol fault",
        "broken pipe", "connection reset"
    ]):
        title = "Связь с автомобилем прервалась или превышен таймаут"
        reason = "В процессе работы прервался обмен данными по USB-кабелю (отошел провод или автомобиль выключил питание)."
        steps = [
            "Проверьте USB-кабель — контакт мог отойти от вибрации.",
            "Нажмите кратковременно педаль тормоза для возобновления подачи питания на ГУ.",
            "Повторите операцию из меню."
        ]
        return title, reason, steps

    # 11. ADB Server / Daemon conflict on computer
    if any(k in raw_lower for k in ["cannot connect to daemon", "connection refused", "failed to start daemon", "address already in use"]):
        title = "Сбой фоновой службы ADB на компьютере"
        reason = "Фоновый процесс adb.exe завис или сетевой порт 5037 на ноутбуке занят сторонней программой."
        steps = [
            "В главном меню выберите пункт [6] (Перезапустить службу ADB).",
            "Закройте на компьютере любые программы синхронизации телефонов (Mi PC Suite, Huawei Suite) и эмуляторы Android."
        ]
        return title, reason, steps

    # Fallback with context
    title = context or "Сбой выполнения операции"
    reason = "Система ГУ не смогла выполнить команду из-за отсутствия связи или блокировки доступа."
    steps = [
        "Проверьте подключение USB-кабеля и активность экрана ГУ (кратковременно нажмите педаль тормоза).",
        "В главном меню выберите пункт [3] (Проверить статус ГУ) для диагностики."
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
        check_text = (str(reason or "") + " " + str(raw or "") + " " + str(title or "")).strip()
        check_lower = check_text.lower()

        # Check if text contains technical ADB / OS error signatures
        has_tech = any(k in check_lower for k in [
            "failed to get feature set", "no devices", "device offline",
            "not found", "unauthorized", "must be root", "remount failed",
            "read-only", "cannot connect", "broken pipe", "connection reset",
            "install_failed", "install_parse_failed", "failure [", "permission denied",
            "adb: error", "adbd cannot", "timeoutexpired", "timed out", "error: closed"
        ])

        if has_tech or not reason:
            h_title, h_reason, h_steps = humanize_adb_error(check_text, context=title)
            final_title = h_title if (not title or any(w in title.lower() for w in ["ошибка", "сбой", "adb", "не удалось"])) else title
            final_reason = h_reason
            final_steps = steps if (steps and len(steps) > 1 and not has_tech) else h_steps
            final_raw = raw or (reason if reason != h_reason else "") or title
        else:
            final_title = title
            final_reason = reason
            final_steps = steps or []
            final_raw = raw

        details = {
            "title": final_title,
            "reason": final_reason,
            "steps": final_steps,
            "raw": str(final_raw).strip() if final_raw else ""
        }
        with self.lock:
            self.status = "error"
            self.status_message = final_title
            self.last_error_details = details
        self.log(final_title, level="error")

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


def _save_emulator_state(state, state_file):
    try:
        tmp = state_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, state_file)
    except Exception:
        pass


def run_emulator_adb(args):
    """
    If Head Unit emulator is active (port published in .emulator_port),
    routes ADB commands directly to the emulator in real time via loopback IPC.
    """
    port_file = os.path.join(BASE_DIR, ".emulator_port")
    if not os.path.isfile(port_file):
        return None

    try:
        with open(port_file, "r", encoding="utf-8") as f:
            port = int(f.read().strip())
    except Exception:
        return None

    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.35)
        s.connect(("127.0.0.1", port))
        payload = json.dumps({"action": args[0] if args else "", "args": args})
        s.sendall(payload.encode("utf-8") + b"\n")
        raw = b""
        while b"\n" not in raw:
            chunk = s.recv(1024)
            if not chunk:
                break
            raw += chunk
        s.close()
        if raw:
            data = json.loads(raw.decode("utf-8").strip())
            return data.get("code", 0), data.get("out", ""), data.get("err", "")
    except (ConnectionRefusedError, socket.timeout):
        try:
            if os.path.isfile(port_file):
                os.remove(port_file)
        except Exception:
            pass
    except Exception:
        pass

    return None


def _legacy_emulator_fallback(args):

    state_file = os.path.join(BASE_DIR, ".emulator_state.json")
    if not os.path.isfile(state_file):
        return None

    state = None
    for _ in range(3):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            break
        except Exception:
            time.sleep(0.03)

    if not state or not state.get("active"):
        return None

    now = time.time()
    if now - state.get("timestamp", 0) > 60.0:
        return None

    action = args[0] if args else ""
    is_rebooting = now < state.get("rebooting_until", 0.0)
    window_end = state.get("window_end", 0.0)
    in_reset_window = (now < window_end) if window_end > 0 else (state.get("in_reset_window", False) and state.get("window_remaining", 0) > 0)
    cable_ok = state.get("cable_connected", True)
    jumper_ok = state.get("jumper_inserted", True)
    vhal_ok = state.get("vhal_unlocked", False)
    toggle_ok = state.get("toggle_active", True) if state.get("toggle_installed", False) else True
    adb_open = cable_ok and not is_rebooting and (vhal_ok or (in_reset_window and jumper_ok)) and toggle_ok

    profile = state.get("profile", "2.1.4.5")

    if not cable_ok:
        if action == "devices":
            return 0, "List of devices attached\n\n", ""
        return 1, "", "error: no devices/emulators found"

    if action == "devices":
        if not adb_open:
            return 0, "List of devices attached\n\n", ""
        return 0, "List of devices attached\nGEELY-EX5-EMULATOR\tdevice\n", ""

    if action == "get-state":
        if is_rebooting:
            return 1, "", "error: device offline"
        if not adb_open:
            return 1, "", "error: no devices/emulators found"
        return 0, "device", ""

    if not adb_open:
        return 1, "", "error: device not found (ADB is closed)"

    if action == "root":
        if profile == "2.2.0" and not state.get("gt_root_forced"):
            return 1, "", "adbd cannot run as root in production builds"
        return 0, "adbd is already running as root", ""

    if action == "wait-for-device":
        return 0, "", ""

    if action == "remount":
        state["remounted_rw"] = True
        _save_emulator_state(state, state_file)
        return 0, "remount succeeded", ""

    if action == "reboot":
        state["rebooting_until"] = now + 4.0
        state["remounted_rw"] = False
        state["gt_root_forced"] = False
        _save_emulator_state(state, state_file)
        return 0, "", ""

    if action == "push":
        dest = args[2] if len(args) > 2 else ""
        return 0, f"1 file pushed: {dest}", ""

    if action == "install":
        state["toggle_installed"] = True
        _save_emulator_state(state, state_file)
        return 0, "Success", ""

    if action == "shell":
        cmd = " ".join(args[1:]) if len(args) > 1 else ""

        if "toggle_disable" in cmd or "persist.adb.enable 0" in cmd:
            state["toggle_active"] = False
            _save_emulator_state(state, state_file)
            return 0, "ADB disabled via Toggle", ""

        if "toggle_enable" in cmd or "persist.adb.enable 1" in cmd:
            state["toggle_active"] = True
            _save_emulator_state(state, state_file)
            return 0, "ADB enabled via Toggle", ""

        if cmd == "id -u":
            if profile == "2.2.0" and not state.get("gt_root_forced"):
                return 0, "2000", ""
            return 0, "0", ""

        if "service.adb.root 1" in cmd:
            state["gt_root_forced"] = True
            _save_emulator_state(state, state_file)
            return 0, "", ""

        if cmd.startswith("getprop ro.product.model"):
            return 0, "Geely EX5 EM-i", ""

        if cmd.startswith("getprop ro.build.display.id"):
            if profile == "early":
                return 0, "FlymeAuto-2.1.0-e245", ""
            elif profile == "2.1.4.5":
                return 0, "FlymeAuto-2.1.4.5-e245_eu", ""
            return 0, "FlymeAuto-2.2.0-GMC-p145", ""

        if cmd.startswith("getprop ro.vendor.ecarx.app_verify"):
            if profile in ["early", "2.2.0"]:
                return 0, "", ""
            return 0, "false" if state.get("parrot_disabled") else "true", ""

        if cmd.startswith("getprop ro.boot.veritymode"):
            return 0, "enforcing" if profile == "2.2.0" else "disabled", ""

        if cmd.startswith("getprop sys.boot_completed"):
            if now < state.get("rebooting_until", 0.0):
                return 0, "0", ""
            return 0, "1", ""

        if "[ -d /system/etc/security/parrot ]" in cmd:
            has_dir = profile in ["early", "2.1.4.5"]
            return 0, "1" if has_dir else "0", ""

        if "557872680" in cmd:
            if profile == "2.2.0" and not state.get("gt_root_forced"):
                return 1, "Must be root to access vehicle HAL", ""
            if not jumper_ok:
                return 1, "VHAL: Jumper not detected, hardware strap missing", ""
            state["vhal_unlocked"] = True
            _save_emulator_state(state, state_file)
            return 0, "Set property: 557872680 to i: 0 a: 0", ""

        if "pm list packages -e" in cmd:
            if state.get("verifier_disabled"):
                return 0, "", ""
            return 0, "package:com.ecarx.xsfinstallverifier", ""

        if "pm list packages" in cmd:
            pkgs = ["package:com.android.settings", "package:com.ecarx.system"]
            if state.get("toggle_installed"):
                pkgs.append("package:com.yahooeu2k.ex5.adbtoggle")
            return 0, "\n".join(pkgs), ""

        if "pm disable-user" in cmd and "com.ecarx.xsfinstallverifier" in cmd:
            state["verifier_disabled"] = True
            _save_emulator_state(state, state_file)
            return 0, "Package com.ecarx.xsfinstallverifier new state: disabled-user", ""

        if "gt-unlock.sh" in cmd:
            if "rescue" in cmd:
                state["scratch_parked"] = True
                _save_emulator_state(state, state_file)
                return 0, "GT:REBOOT", ""

            state["verifier_disabled"] = True
            if profile == "early":
                _save_emulator_state(state, state_file)
                return 0, "Проверка подписи Parrot: на этой прошивке она включена всегда и выключателя не имеет\nGT:PARROT", ""

            if profile == "2.1.4.5":
                if not state.get("remounted_rw"):
                    _save_emulator_state(state, state_file)
                    return 0, "Проверяющий установок (AutoInstallVerifier): выключен\nПроверка подписи Parrot: включена, открываю системные разделы\nGT:REMOUNT", ""
                else:
                    state["parrot_disabled"] = True
                    _save_emulator_state(state, state_file)
                    return 0, "Проверка подписи Parrot: выключена в файле, нужна перезагрузка\nGT:REBOOT", ""

            if profile == "2.2.0":
                state["scratch_parked"] = True
                if not state.get("mark_remount"):
                    state["mark_remount"] = True
                    _save_emulator_state(state, state_file)
                    return 0, "Проверяющий установок (AutoInstallVerifier): нет или уже выключен\nПроверка подписи Parrot: на этой прошивке её нет\nСлой прежней прошивки отодвинут в разделе scratch\nОткрываю системные разделы для нижней панели и медиамоста\nGT:REMOUNT", ""
                else:
                    state["mark_remount"] = False
                    _save_emulator_state(state, state_file)
                    return 0, "Проверка подписи Parrot: на этой прошивке её нет\nGT:OK", ""

        if "/system/etc/security/parrot/" in cmd:
            _save_emulator_state(state, state_file)
            return 0, "", ""

        return 0, "", ""

    return 0, "", ""


def run_adb(args, timeout=30):
    """Executes an adb command safely without opening popup windows and with robust UTF-8 encoding."""
    # 0. Check virtual stand emulator
    emu_res = run_emulator_adb(args)
    if emu_res is not None:
        return emu_res

    if not STATE.adb_path or not os.path.isfile(STATE.adb_path):
        locate_or_download_adb()
        if not STATE.adb_path:
            return -1, "", "ADB недоступен"

    cmd = [STATE.adb_path] + args
    try:
        creationflags = 0x08000000 if STATE.os_name == "windows" else 0
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
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
        if STATE.adb_path and os.path.isfile(STATE.adb_path):
            subprocess.run([STATE.adb_path, "kill-server"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass
    try:
        if STATE.os_name == "windows":
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["killall", "-9", "adb"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(1)
    code, stdout, stderr = run_adb(["start-server"], timeout=10)
    if code == 0:
        STATE.set_status("success", "Служба ADB успешно перезапущена с нуля")
        STATE.log("Служба ADB перезапущена с нуля", "success")
    else:
        title, reason, steps = humanize_adb_error(stderr or stdout, context="Не удалось запустить сервер ADB")
        STATE.set_error(title, reason, steps, raw=stderr or stdout)


def stop_adb_server():
    """Completely terminates ADB server processes so that the browser (WebUSB) can exclusively access the vehicle."""
    STATE.log("Останавливаем службу ADB для освобождения USB-разъёма...", "cmd")
    try:
        if STATE.adb_path and os.path.isfile(STATE.adb_path):
            subprocess.run([STATE.adb_path, "kill-server"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass
    try:
        if STATE.os_name == "windows":
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["killall", "-9", "adb"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    STATE.device_state = "disconnected"
    STATE.device_serial = None
    STATE.log("Фоновая служба ADB остановлена. USB-порт полностью передан браузеру.", "success")


def reclaim_adb_connection(retries=4, delay=0.8):
    """
    Terminates any rogue or orphaned ADB processes, restarts the daemon,
    and attempts to reclaim the USB connection from the browser.
    Returns True if a device is successfully detected, False otherwise.
    """
    STATE.log("Перехватываем управление USB-портом: перезапуск службы ADB...", "cmd")
    kill_adb_processes()
    time.sleep(0.5)
    for _ in range(retries):
        if check_devices():
            return True
        time.sleep(delay)
    return False


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
        STATE.last_test = None
        return False


def ensure_root(timeout=60):
    """
    Ensures root access (UID 0), handling cases where adbd restarts after boot
    or drops root privileges on newer 2.2.0 / GMC firmwares.
    Matches gt_root logic from the official GeelyTune unlock scripts.
    """
    code_r, out_r, _ = run_adb(["root"], timeout=10)
    time.sleep(1)
    run_adb(["wait-for-device"], timeout=5)

    code_id, out_id, _ = run_adb(["shell", "id", "-u"], timeout=5)
    if code_id == 0 and out_id.strip() == "0":
        return True

    # If UID != 0 or adbd cannot run as root directly, retry loop with service restart
    start_time = time.time()
    iteration = 0
    while time.time() - start_time < timeout:
        if STATE.stop_worker:
            return False
        if iteration % 8 == 0:
            run_adb(["shell", "setprop service.adb.root 1; setprop ctl.restart adbd"], timeout=5)
        time.sleep(1)
        code_id, out_id, _ = run_adb(["shell", "id", "-u"], timeout=5)
        if code_id == 0 and out_id.strip() == "0":
            return True
        iteration += 1

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
    if len(connected_devs) > 1:
        STATE.log(f"⚠️ Внимание: к ноутбуку подключено несколько устройств ({len(connected_devs)}). Отключите посторонние телефоны/планшеты.", "warning")
    STATE.log(f"✅ Автомобиль успешно подключен! Серийный номер: {serial}", "success")

    # 2. Test root access
    STATE.log("🔑 Проверка доступа суперпользователя (adb root)...", "cmd")
    root_ok = ensure_root(timeout=8)
    if root_ok:
        STATE.log("✅ Root-доступ подтверждён (UID: 0).", "success")
    else:
        code_id, out_id, _ = run_adb(["shell", "id", "-u"], timeout=3)
        STATE.log(f"⚠️ Root-доступ ограничен или не предоставлен (UID: {out_id or 'неизвестно'}).", "warning")

    # 3. Read firmware & system properties
    STATE.log("📋 Считывание сведений об устройстве (ADB getprop)...", "cmd")
    _, fw_build, _ = run_adb(["shell", "getprop", "ro.build.display.id"], timeout=5)
    _, fw_inc, _ = run_adb(["shell", "getprop", "ro.build.version.incremental"], timeout=5)
    _, model, _ = run_adb(["shell", "getprop", "ro.product.model"], timeout=5)
    _, android_rel, _ = run_adb(["shell", "getprop", "ro.build.version.release"], timeout=5)

    build_id = (fw_build.strip() or fw_inc.strip())
    android_ver = android_rel.strip()
    model_info = model.strip() or "Штатное ГУ Geely"

    if android_ver and build_id:
        os_info = f"Android {android_ver} ({build_id})"
    elif android_ver:
        os_info = f"Android {android_ver}"
    elif build_id:
        os_info = build_id
    else:
        os_info = "ОС Android"

    STATE.log(f"🚘 Модель ГУ: {model_info} | {os_info}", "info")

    # 4. Check Parrot app_verify and firmware generation
    _, parrot_val, _ = run_adb(["shell", "getprop", "ro.vendor.ecarx.app_verify"], timeout=5)
    parrot_val = parrot_val.strip().lower()
    code_pdir, out_pdir, _ = run_adb(["shell", "[ -d /system/etc/security/parrot ] && echo 1 || echo 0"], timeout=5)
    has_parrot_dir = (code_pdir == 0 and out_pdir.strip() == "1")

    if parrot_val == "true":
        parrot_locked = True
        parrot_status_desc = "locked"
        fw_family = "Ветка ~2.1.4.5+ (Parrot отключаемый)"
        STATE.log("🔒 Защита Parrot: ВКЛЮЧЕНА (ветка ~2.1.4.5+ под маской T1.0.0; ориентир: мини-значки обогрева лобового в климате внизу).", "warning")
    elif parrot_val == "false":
        parrot_locked = False
        parrot_status_desc = "disabled"
        fw_family = "Ветка ~2.1.4.5+ (Parrot уже выключен)"
        STATE.log("🔓 Защита Parrot: ВЫКЛЮЧЕНА (ветка ~2.1.4.5+, установка любых APK разрешена).", "success")
    elif has_parrot_dir:
        parrot_locked = True
        parrot_status_desc = "hardcoded"
        fw_family = "Ветка ~2.1.3 / ранняя (Parrot вшит намертво)"
        STATE.log("ℹ️ Защита Parrot: РАННЯЯ ВЕТКА ~2.1.3 (под маской T1.0.0; защита вшита намертво без выключателя).", "warning")
        STATE.log("💡 На этой прошивке нет лимита скорости и нет мини-значков обогрева лобового в строке климата.", "info")
    else:
        parrot_locked = False
        parrot_status_desc = "absent"
        fw_family = "Ветка ~2.2.0 / GMC (Parrot отсутствует)"
        STATE.log("🔓 Защита Parrot: ОТСУТСТВУЕТ (ветка ~2.2.0 / GMC под маской T1.0.0; ориентир: пункт «Лимит скорости» в меню ГУ).", "success")

    if android_ver:
        os_info = f"Android {android_ver} • {fw_family}"
    else:
        os_info = fw_family

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
        STATE.log("💡 Достаточно запустить экспресс-снятие ограничений в 1 клик (подходит для 2.1.4.5, 2.2.0 и GMC).", "success")
    else:
        recommendation = "ready"
        STATE.log("🎉 ВЕРДИКТ: Все блокировки уже сняты! ГУ готово к установке любых приложений и твиков GeelyTune.", "success")

    res = {
        "ok": True,
        "connected": True,
        "serial": serial,
        "model": model_info,
        "firmware": os_info,
        "os_info": os_info,
        "root_ok": root_ok,
        "parrot_locked": parrot_locked,
        "parrot_status_desc": parrot_status_desc,
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
    """Continuously waits for device reboot, grants root, and sets VHAL property with adaptive 2.2.0 support."""
    STATE.set_status("working", "Ожидание перезагрузки ГУ после сброса настроек... Не закрывайте окно!", 2)
    STATE.log("ВНИМАНИЕ: На экране авто перейдите: «Основное приложение» ➔ «Мой автомобиль» ➔ «Сброс к заводским настройкам» и согласитесь с предупреждениями.", "warning")
    STATE.log("💡 Как это работает: при сбросе система кратковременно открывает 20-секундное сервисное окно. Программа непрерывно сканирует USB и молниеносно фиксирует постоянный ADB.", "info")

    vhal_cmd = "/system/bin/lshal debug android.hardware.automotive.vehicle@2.0::IVehicle/default --set 557872680 i 0 a 0"
    attempt = 0

    while not STATE.stop_worker:
        code, stdout, _ = run_adb(["get-state"], timeout=2)
        if code != 0 or stdout != "device":
            time.sleep(0.2)
            continue

        attempt += 1
        STATE.log(f"⚡ Устройство обнаружено на шине USB! Попытка перехвата сервисного окна #{attempt}...", "cmd")

        # Fast multi-attempt loop inside the open 20-second window
        window_start = time.time()
        while time.time() - window_start < 25 and not STATE.stop_worker:
            # 1. Immediate root request
            run_adb(["root"], timeout=3)

            # 2. Immediately send VHAL command directly without wasting time on remount
            code, out, err = run_adb(["shell", vhal_cmd], timeout=4)
            combined_out = f"{out} {err}".strip()

            if "Set property" in combined_out:
                play_sound("catch")
                STATE.log("🎉 УСПЕХ! Автомобиль подтвердил фиксацию порта (Set property)! Постоянный ADB активирован.", "success")
                STATE.set_status("success", "ADB зафиксирован! Перемычку НЕ трогаем. Подтвердите перезагрузку ГУ.", 3)
                return

            if "Must be root" in combined_out or "cannot run as root" in combined_out:
                # Trigger internal adbd root restart (crucial for 2.2.0 firmwares)
                run_adb(["shell", "setprop service.adb.root 1; setprop ctl.restart adbd"], timeout=2)
                time.sleep(0.4)
            elif combined_out:
                STATE.log(f"Ответ системы ГУ: {combined_out}")
                time.sleep(0.4)
            else:
                time.sleep(0.3)

        STATE.log("⚠️ Сервисное окно (20 сек) завершилось. Если окно закрылось раньше фиксации — снова нажмите «Сброс к заводским настройкам» на экране авто (скрипт продолжает сканирование)...", "warning")
        time.sleep(1)


# ==================== STEP 3: REBOOT & VERIFY ====================
def worker_reboot_and_verify():
    """Reboots HU and waits for full boot (jumper safely remains in place)."""
    STATE.set_status("working", "Перезагрузка ГУ (экран погаснет, это норма!). Ожидаем загрузку...", 3)
    STATE.log("⚠️ ВНИМАНИЕ: ЭКРАН АВТОМОБИЛЯ СЕЙЧАС ПОГАСНЕТ И ПЕРЕЗАГРУЗИТСЯ!", "warning")
    STATE.log("💡 Это абсолютно нормальный штатный процесс: ГУ перезагружается для сохранения постоянного ADB.", "info")
    STATE.log("⏳ Пожалуйста, не пугайтесь и ничего не трогайте! Экран мультимедиа включится сам через 1.5 - 2 минуты.", "info")
    STATE.log("🔌 Провод USB и сервисную перемычку оставляем на месте, питание автомобиля не выключаем.", "info")

    # Read current boot session id before reboot to prevent catching stale status
    _, prev_boot_id, _ = run_adb(["shell", "cat", "/proc/sys/kernel/random/boot_id"], timeout=5)
    prev_boot_id = prev_boot_id.strip()

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
                    "При необходимости кратковременно нажмите педаль тормоза для подачи питания."
                ],
                raw="Boot verification timeout (300s)"
            )
            return

        code, out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
        if code == 0 and out.strip() == "1":
            if prev_boot_id:
                _, cur_boot_id, _ = run_adb(["shell", "cat", "/proc/sys/kernel/random/boot_id"], timeout=5)
                cur_boot_id = cur_boot_id.strip()
                if cur_boot_id and cur_boot_id == prev_boot_id:
                    time.sleep(3)
                    continue

            STATE.log("✅ Экран автомобиля включился и полностью загрузился! Проверяем постоянство связи ADB...", "success")
            time.sleep(2)
            check_devices()
            if STATE.device_state == "connected":
                STATE.log("🎉 Связь подтверждена! ADB стабильно активен в системе ГУ.", "success")
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
    root_ok = ensure_root(timeout=60)
    if not root_ok:
        title, reason, steps = humanize_adb_error("must be root", context="Отсутствуют права суперпользователя (root) на ГУ")
        STATE.set_error(title, reason, steps, raw="UID != 0 after ensure_root")
        return

    # 3. Push script
    STATE.log("📂 Загрузка системного скрипта разблокировки (unlock-hu.sh) на ГУ...", "cmd")
    STATE.log("💡 Пояснение: универсальный скрипт для 2.1.4.5 и 2.2.0. Он отключает защиту Parrot/AutoInstallVerifier, подготавливает системные разделы и изолирует старые оверлеи в scratch.", "info")
    code, out_p, err_p = run_adb(["push", unlock_script, "/data/local/tmp/gt-unlock.sh"], timeout=15)
    if code != 0:
        title, reason, steps = humanize_adb_error(err_p or out_p, context="Ошибка загрузки скрипта на ГУ")
        STATE.set_error(title, reason, steps, raw=err_p or out_p)
        return

    # Run loop
    unlocked_ok = False
    is_early_parrot = False
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
            STATE.log("✅ Все системные ограничения успешно сняты!", "success")
            STATE.log("💡 Теперь система автомобиля позволит устанавливать любые стандартные Android APK: каталог софта доступен на https://ex5app.wingie.ru/ (автор — @wingus) или свои APK.", "info")
            unlocked_ok = True
            break
        elif "GT:PARROT" in out:
            run_adb(["shell", "rm", "-f", "/data/local/tmp/gt-unlock.sh"], timeout=5)
            STATE.log("ℹ️ Обнаружена заводская ранняя ветка 2.1.3 (под маской T1.0.0; Parrot вшит в систему).", "info")
            STATE.log("🔑 Защита Parrot в этой версии не имеет глобального выключателя. Автоматически применяем технологию Parrot Trust...", "cmd")
            STATE.log("📦 Внедряем доверенный ключ для переключателя Geely-ADB-Toggle...", "cmd")

            toggle_apk = apk_file
            if not os.path.isfile(toggle_apk):
                toggle_apk = get_resource_path("Geely-ADB-Toggle-1.1.0.apk")
            if not os.path.isfile(toggle_apk):
                toggle_apk = os.path.join(CURRENT_DIR, "Geely-ADB-Toggle-1.1.0.apk")
            if not os.path.isfile(toggle_apk):
                toggle_apk = os.path.join(ROOT_DIR, "core", "Geely-ADB-Toggle-1.1.0.apk")

            if os.path.isfile(toggle_apk):
                worker_install_via_parrot_trust(toggle_apk, "Geely-ADB-Toggle-1.1.0")
            else:
                STATE.set_error("Файл Geely-ADB-Toggle не найден", "Не найден APK-файл переключателя для установки через доверенный сертификат.")
                return

            if STATE.status == "error":
                return

            unlocked_ok = True
            is_early_parrot = True
            break
        elif "GT:REMOUNT" in out:
            STATE.log("🔄 Открываем системный раздел диска ГУ для записи (remount)...", "info")
            run_adb(["remount"], timeout=15)
            time.sleep(2)
        elif "GT:REBOOT" in out:
            STATE.set_status("working", "Перезагрузка ГУ (экран погаснет, это норма!). Ожидаем загрузку...", 4)
            STATE.log("⚠️ ВНИМАНИЕ: ЭКРАН АВТОМОБИЛЯ СЕЙЧАС ПОГАСНЕТ И ПЕРЕЗАГРУЗИТСЯ!", "warning")
            STATE.log("💡 Это абсолютно нормальный штатный процесс: система автомобиля применяет системные разделы.", "info")
            STATE.log("⏳ Пожалуйста, не пугайтесь и ничего не трогайте! Экран мультимедиа включится сам через 1.5 - 2 минуты.", "info")
            STATE.log("🔌 Кабель USB не трогаем, питание авто не выключаем. Программа автоматически продолжит настройку...", "info")

            # Read current boot session id prior to reboot to prevent premature resume
            _, prev_boot_id, _ = run_adb(["shell", "cat", "/proc/sys/kernel/random/boot_id"], timeout=5)
            prev_boot_id = prev_boot_id.strip()

            run_adb(["reboot"], timeout=10)
            time.sleep(15)
            reboot_start = time.time()
            reboot_ok = False
            rescue_attempted = False
            while not STATE.stop_worker:
                elapsed = time.time() - reboot_start
                if elapsed > 300:
                    if not rescue_attempted:
                        rescue_attempted = True
                        STATE.log("⚠️ ГУ не загрузилось за 5 минут — активируем режим спасения (проверяем/отодвигаем слой прежней прошивки в scratch)...", "warning")
                        ensure_root(timeout=15)
                        code_res, out_res, _ = run_adb(["shell", "sh", "/data/local/tmp/gt-unlock.sh", "rescue"], timeout=60)
                        for rline in out_res.splitlines():
                            if rline.strip() and not rline.strip().startswith("GT:"):
                                STATE.log(rline.strip())
                        if "GT:REBOOT" in out_res:
                            STATE.log("🔄 Конфликтный слой отодвинут, отправляем ГУ в повторную перезагрузку...", "info")
                            run_adb(["reboot"], timeout=10)
                            time.sleep(15)
                            reboot_start = time.time()
                            continue
                    STATE.set_error(
                        title="Превышено время перезагрузки ГУ (таймаут 5 минут)",
                        reason="Головное устройство не вышло на связь после команды перезагрузки.",
                        steps=[
                            "Убедитесь, что экран мультимедиа автомобиля включился и загрузился.",
                            "Проверьте надежность подключения кабеля USB-A к порту ГУ и ноутбука.",
                            "Кратковременно нажмите на педаль тормоза для подачи питания."
                        ],
                        raw="Reboot timeout exceeded 300s"
                    )
                    return
                c, b_out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
                if c == 0 and b_out.strip() == "1":
                    if prev_boot_id:
                        _, cur_boot_id, _ = run_adb(["shell", "cat", "/proc/sys/kernel/random/boot_id"], timeout=5)
                        cur_boot_id = cur_boot_id.strip()
                        if cur_boot_id and cur_boot_id == prev_boot_id:
                            time.sleep(3)
                            continue
                    reboot_ok = True
                    STATE.log("✅ Экран автомобиля включился и успешно загрузился! Продолжаем выполнение процедур...", "success")
                    break
                time.sleep(3)
            if not reboot_ok or STATE.stop_worker:
                return
            ensure_root(timeout=60)
            run_adb(["wait-for-device"], timeout=10)
        else:
            # Check if device was in the middle of unexpected reboot
            code_st, out_st, _ = run_adb(["get-state"], timeout=2)
            if code_st != 0 or out_st.strip() != "device":
                STATE.set_status("working", "ГУ ушло в перезагрузку (экран погас, это норма!). Ждём...", 4)
                STATE.log("⚠️ Экран автомобиля ушел в перезагрузку. Ожидаем включения мультимедиа (около 1.5 - 2 мин)...", "warning")
                reboot_start = time.time()
                recovered = False
                while not STATE.stop_worker and (time.time() - reboot_start < 240):
                    c, b_out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
                    if c == 0 and b_out.strip() == "1":
                        recovered = True
                        STATE.log("✅ Экран авто снова включился и загрузился! Продолжаем настройку...", "success")
                        ensure_root(timeout=30)
                        break
                    time.sleep(3)
                if recovered:
                    continue

            title, reason, steps = humanize_adb_error(out, context="Непредвиденный ответ скрипта разблокировки")
            STATE.set_error(title, reason, steps, raw=out)
            return

    if not unlocked_ok:
        title, reason, steps = humanize_adb_error(out, context="Не удалось завершить снятие ограничений за 8 проходов")
        STATE.set_error(title, reason, steps, raw=out)
        return

    # If installed via Parrot Trust, finish with dedicated guidance
    if is_early_parrot:
        final_parrot_locked = True
        final_verifier_active = False
        if STATE.last_test and isinstance(STATE.last_test, dict):
            STATE.last_test["parrot_locked"] = True
            STATE.last_test["parrot_status_desc"] = "hardcoded"
            STATE.last_test["verifier_active"] = False
            STATE.last_test["toggle_installed"] = True
            STATE.last_test["needs_unlock"] = False
            STATE.last_test["recommendation"] = "ready"
            STATE.last_test["message"] = "Переключатель установлен через доверенный сертификат!"
        STATE.set_status("success", "Переключатель Geely-ADB-Toggle успешно установлен через доверенный сертификат!", 5)
        STATE.log("🏆 ВСЕ ЭТАПЫ РАЗБЛОКИРОВКИ ВЫПОЛНЕНЫ! Переключатель Geely-ADB-Toggle установлен в ГУ.", "success")
        STATE.log("💡 На ветке 2.1.3 защита Parrot вшита намертво: для установки других сторонних APK (Яндекс, плееры) используйте пункт [T] в меню — он добавит сертификат и установит приложение в 1 клик.", "info")
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
        STATE.log("🔓 Защита Parrot certificates: ВЫКЛЮЧЕНА / НЕ ТРЕБУЕТСЯ (установка APK разрешена)", "success")
    if not final_verifier_active:
        STATE.log("🔓 Системный верификатор AutoInstallVerifier: ОТКЛЮЧЕН", "success")

    # Update STATE.last_test so UI reflects unlocked status
    if STATE.last_test and isinstance(STATE.last_test, dict):
        STATE.last_test["parrot_locked"] = final_parrot_locked
        STATE.last_test["parrot_status_desc"] = "disabled" if parrot_check.strip().lower() == "false" else ("absent" if not parrot_check.strip() else "locked")
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
            "firmware": (STATE.last_test.get("os_info") or "ОС Android") if STATE.last_test else "ОС Android",
            "os_info": (STATE.last_test.get("os_info") or "ОС Android") if STATE.last_test else "ОС Android",
            "root_ok": True,
            "parrot_locked": final_parrot_locked,
            "parrot_status_desc": "absent" if not parrot_check.strip() else "disabled",
            "verifier_active": final_verifier_active,
            "toggle_installed": True,
            "needs_unlock": False,
            "recommendation": "ready",
            "message": "ГУ полностью разблокировано!"
        }

    STATE.set_status("success", "Поздравляем! Разблокировка полностью завершена!", 5)
    STATE.log("🏆 ВСЕ ЭТАПЫ РАЗБЛОКИРОВКИ ВЫПОЛНЕНЫ! Ограничения сняты: ставьте приложения с https://ex5app.wingie.ru/ (от @wingus), свои APK или твики GeelyTune.", "success")


# ==================== PARROT TRUST (FOR EARLY FIRMWARES < 2.1.4.5) ====================
def extract_apk_cert_pem(apk_path):
    """
    Extracts signing certificate from APK (APK Signature Scheme v2/v3 or v1 JAR)
    and formats it as X.509 PEM. Zero external dependencies.
    """
    import struct
    import base64
    import zipfile

    if not os.path.isfile(apk_path):
        return None

    try:
        with open(apk_path, "rb") as f:
            data = f.read()

        def lp(buf, off):
            n = struct.unpack_from("<I", buf, off)[0]
            return buf[off + 4:off + 4 + n], off + 4 + n

        # 1. Try APK Signature Scheme v2 / v3
        eocd = data.rfind(b"PK\x05\x06")
        if eocd >= 0:
            cd = struct.unpack_from("<I", data, eocd + 16)[0]
            if cd >= 24 and data[cd - 16:cd] == b"APK Sig Block 42":
                size = struct.unpack_from("<Q", data, cd - 24)[0]
                off, end = cd - size, cd - 24
                pairs = {}
                while off < end:
                    n = struct.unpack_from("<Q", data, off)[0]
                    pid = struct.unpack_from("<I", data, off + 8)[0]
                    pairs[pid] = data[off + 12:off + 8 + n]
                    off += 8 + n
                for pid in (0xF05368C0, 0x7109871A):
                    if pid in pairs:
                        signers, _ = lp(pairs[pid], 0)
                        signer, _ = lp(signers, 0)
                        signed, _ = lp(signer, 0)
                        _, o = lp(signed, 0)
                        certs, _ = lp(signed, o)
                        cert, _ = lp(certs, 0)
                        b64 = base64.b64encode(cert).decode("ascii")
                        lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
                        return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"

        # 2. Fallback to v1 JAR signature (Windows PowerShell SignedCms)
        if STATE.os_name == "windows":
            with zipfile.ZipFile(apk_path) as z:
                sig_name = next((n for n in z.namelist() if n.startswith("META-INF/") and n.rsplit(".", 1)[-1].upper() in ("RSA", "DSA", "EC")), None)
                if sig_name:
                    sig_bytes = z.read(sig_name)
                    b64_sig = base64.b64encode(sig_bytes).decode("ascii")
                    ps_script = (
                        "Add-Type -AssemblyName System.Security; "
                        f"$bytes = [Convert]::FromBase64String('{b64_sig}'); "
                        "$cms = New-Object Security.Cryptography.Pkcs.SignedCms; "
                        "$cms.Decode($bytes); "
                        "[Convert]::ToBase64String($cms.Certificates[0].RawData)"
                    )
                    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], stdout=subprocess.PIPE, text=True, timeout=10)
                    if res.returncode == 0 and res.stdout.strip():
                        b64 = res.stdout.strip().replace("\r", "").replace("\n", "")
                        lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
                        return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"
    except Exception as e:
        STATE.log(f"Предупреждение при анализе подписи: {e}", "warning")

    return None


def worker_install_via_parrot_trust(apk_path, app_name=None):
    """
    Installs an APK on early firmware (pre-2.1.4.5) by extracting its certificate,
    pushing it into /system/etc/security/parrot/<name>.x509.pem, rebooting HU,
    and installing the package.
    """
    import re

    if not os.path.isfile(apk_path):
        STATE.set_error("Файл APK не найден", f"Не найден указанный файл: {apk_path}", ["Проверьте путь к файлу."])
        return

    base_apk = os.path.basename(apk_path)
    if not app_name:
        app_name = os.path.splitext(base_apk)[0]
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", app_name)
    target_pem = f"/system/etc/security/parrot/{safe_name}.x509.pem"

    STATE.set_status("working", f"Установка {base_apk} через Parrot Trust...")
    STATE.log(f"📦 Анализ файла приложения: {base_apk}...", "cmd")

    pem = extract_apk_cert_pem(apk_path)
    if not pem:
        STATE.set_error("Сертификат не извлечён", "Не удалось извлечь цифровую подпись из APK-файла.", ["Убедитесь, что APK корректно подписан."])
        return

    # Check for public test key
    is_public = "android@android.com" in pem or "Android Open Source Project" in pem
    if is_public:
        STATE.log("ℹ️ Приложение подписано общедоступным тестовым ключом Android — добавление сертификата не требуется.", "info")
    else:
        STATE.log("🔑 Цифровая подпись успешно извлечена из APK!", "success")
        STATE.log(f"📂 Запись сертификата в хранилище доверенных ключей ГУ: {target_pem}...", "cmd")

        ensure_root(timeout=15)
        code_rem, out_rem, err_rem = run_adb(["remount"], timeout=15)
        if "reboot" in (out_rem + err_rem).lower():
            STATE.set_status("working", "Перезагрузка ГУ для remount (экран погаснет, это норма!)...")
            STATE.log("⚠️ ВНИМАНИЕ: ЭКРАН АВТОМОБИЛЯ СЕЙЧАС ПОГАСНЕТ И ПЕРЕЗАГРУЗИТСЯ!", "warning")
            STATE.log("💡 Это штатный процесс: система автомобиля применяет открытие разделов.", "info")
            STATE.log("⏳ Не пугайтесь и ничего не трогайте! Экран мультимедиа включится сам через 1.5 - 2 минуты.", "info")
            run_adb(["reboot"], timeout=10)
            time.sleep(20)
            start_rem_wait = time.time()
            while not STATE.stop_worker:
                if time.time() - start_rem_wait > 300:
                    STATE.set_error("Таймаут перезагрузки ГУ", "ГУ не загрузилось за 5 минут.", ["Проверьте экран автомобиля."])
                    return
                c, b, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
                if c == 0 and b.strip() == "1":
                    break
                time.sleep(3)
            ensure_root(timeout=30)
            run_adb(["remount"], timeout=15)

        run_adb(["shell", "mkdir -p /system/etc/security/parrot"], timeout=5)

        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_pem = os.path.join(temp_dir, f"{safe_name}.x509.pem")
        try:
            with open(temp_pem, "w", encoding="utf-8") as f:
                f.write(pem)
            code, out, err = run_adb(["push", temp_pem, target_pem], timeout=15)
        finally:
            if os.path.isfile(temp_pem):
                try:
                    os.remove(temp_pem)
                except Exception:
                    pass

        if code != 0:
            title, reason, steps = humanize_adb_error(err or out, context="Ошибка записи сертификата в систему ГУ")
            STATE.set_error(title, reason, steps, raw=err or out)
            return

        run_adb(["shell", f"chown root:root {target_pem} && chmod 644 {target_pem} && restorecon {target_pem}"])
        STATE.set_status("working", "Перезагрузка ГУ для применения сертификата (экран погаснет, это норма!)...")
        STATE.log("✅ Сертификат добавлен в систему!", "success")
        STATE.log("⚠️ ВНИМАНИЕ: ЭКРАН АВТОМОБИЛЯ СЕЙЧАС ПОГАСНЕТ И ПЕРЕЗАГРУЗИТСЯ!", "warning")
        STATE.log("💡 Это штатная перезагрузка ГУ для применения добавленного доверенного ключа.", "info")
        STATE.log("⏳ Не пугайтесь и ничего не трогайте! Экран мультимедиа включится сам через 1.5 - 2 минуты.", "info")
        run_adb(["reboot"], timeout=10)
        time.sleep(20)

        start_wait = time.time()
        booted = False
        while not STATE.stop_worker:
            if time.time() - start_wait > 300:
                STATE.set_error("Таймаут перезагрузки ГУ", "ГУ не загрузилось за 5 минут.", ["Проверьте экран автомобиля."])
                return
            c, b, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
            if c == 0 and b.strip() == "1":
                booted = True
                break
            time.sleep(3)

        if not booted or STATE.stop_worker:
            return

        ensure_root(timeout=30)
        run_adb(["wait-for-device"], timeout=5)

        # Ожидание стабилизации adbd (как в оригинальном trust.bat settle)
        STATE.log("⏳ Проверка стабильности службы adbd перед установкой...", "cmd")
        last_pid = None
        stable_count = 0
        for _ in range(20):
            if STATE.stop_worker:
                return
            _, pid_out, _ = run_adb(["shell", "pidof", "adbd"], timeout=5)
            pid = pid_out.strip()
            if pid and pid == last_pid:
                stable_count += 3
                if stable_count >= 15:
                    break
            else:
                last_pid = pid
                stable_count = 0
            time.sleep(3)

    # Install APK
    STATE.log(f"📱 Установка приложения {base_apk} в систему...", "cmd")
    run_adb(["shell", "settings", "put", "global", "verifier_verify_adb_installs", "0"], timeout=5)

    installed_ok = False
    for attempt in range(1, 5):
        if STATE.stop_worker:
            return
        code_inst, out_inst, err_inst = run_adb(["install", "-r", "--user", "10", apk_path], timeout=90)
        if "Success" in out_inst:
            installed_ok = True
            break
        elif "Failure [" in (out_inst + err_inst):
            c2, o2, _ = run_adb(["install", "-r", apk_path], timeout=90)
            if "Success" in o2:
                installed_ok = True
                break
            STATE.log(f"Попытка {attempt} вернула: {out_inst} {err_inst}. Повторяем...", "warning")
        time.sleep(3)

    if installed_ok:
        play_sound("success")
        STATE.set_status("success", f"Приложение {base_apk} успешно установлено!")
        STATE.log(f"🎉 ГОТОВО: {base_apk} успешно установлено на раннюю прошивку ГУ!", "success")
    else:
        title, reason, steps = humanize_adb_error((out_inst or "") + " " + (err_inst or ""), context=f"Не удалось установить {base_apk}")
        STATE.set_error(title, reason, steps, raw=(out_inst or "") + " " + (err_inst or ""))

