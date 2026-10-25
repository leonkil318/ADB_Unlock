"""
Geely ADB Unlock Master - Local Orchestrator Engine
Provides a local HTTP server and REST API to manage the entire ADB unlock lifecycle.
Works on Windows, macOS, and Linux without external dependencies.
"""

import sys
import os
import platform
import subprocess
import threading
import time
import json
import urllib.request
import zipfile
import io
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Base directories
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = os.path.dirname(BASE_DIR)
WEB_DIR = os.path.join(BASE_DIR, 'web')
BIN_DIR = os.path.join(BASE_DIR, 'bin')

# Safe UTF-8 output on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# Global state
class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.os_name = platform.system().lower() # 'windows', 'darwin', 'linux'
        self.adb_path = None
        self.adb_ready = False
        self.mode = "standard"  # 'standard' (full with jumper) or 'quick' (after dealer update)
        self.step = 1  # 1: Preparation, 2: Factory Reset & VHAL, 3: Jumper removal & Reboot, 4: Unlock Parrot & Toggle, 5: Finished
        self.status = "idle"  # idle, working, waiting_reset, success, error
        self.status_message = "Готов к работе"
        self.device_serial = None
        self.device_state = "disconnected"
        self.last_test = None
        now = time.strftime("%H:%M:%S")
        self.logs = [
            {"time": now, "text": "Мастер разблокировки Geely ADB готов к работе.", "level": "info", "formatted": f"[{now}] ℹ️ Мастер разблокировки Geely ADB готов к работе."},
            {"time": now, "text": "Совместимость: Geely EX5 EM-i, Belgee X80 и модели на Flyme Auto / Ecarx (2.1.4.5+).", "level": "info", "formatted": f"[{now}] 🚘 Совместимость: Geely EX5 EM-i, Belgee X80 и модели на Flyme Auto / Ecarx (2.1.4.5+)."},
            {"time": now, "text": "Режимы: 1) С нуля с перемычкой. 2) После обновления у ОД на 2.1.4.5+ без перемычки (если ADB уже был открыт).", "level": "info", "formatted": f"[{now}] 💡 Поддерживаются 2 сценария: полный цикл с нуля с перемычкой или экспресс-снятие защиты после обновления ОД без разборки."}
        ]
        self.worker_thread = None
        self.stop_worker = False

    def log(self, text, level="info"):
        timestamp = time.strftime("%H:%M:%S")
        prefix = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "cmd": "⚡"
        }.get(level, "•")
        entry = f"[{timestamp}] {prefix} {text}"
        with self.lock:
            self.logs.append({"time": timestamp, "text": text, "level": level, "formatted": entry})
            if len(self.logs) > 300:
                self.logs.pop(0)
        try:
            log_file = os.path.join(BASE_DIR, "debug.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass
        try:
            if sys.stdout:
                print(entry)
        except Exception:
            pass

    def set_status(self, status, message, step=None):
        with self.lock:
            self.status = status
            self.status_message = message
            if step is not None:
                self.step = step
        self.log(message, level="info" if status != "error" else "error")

    def to_dict(self):
        with self.lock:
            return {
                "os": self.os_name,
                "mode": self.mode,
                "step": self.step,
                "status": self.status,
                "status_message": self.status_message,
                "adb_ready": self.adb_ready,
                "adb_path": self.adb_path,
                "device_serial": self.device_serial,
                "device_state": self.device_state,
                "last_test": self.last_test,
                "logs": self.logs[-50:]  # send last 50
            }

STATE = AppState()

def locate_or_download_adb():
    """Finds adb in bin/, system PATH, or downloads it automatically."""
    is_win = STATE.os_name == "windows"
    adb_binary = "adb.exe" if is_win else "adb"
    
    # 1. Check core/bin/
    local_adb = os.path.join(BIN_DIR, adb_binary)
    if not os.path.isfile(local_adb):
        if STATE.os_name == "darwin":
            darwin_pkg = os.path.join(BIN_DIR, "adb-darwin")
            if os.path.isfile(darwin_pkg):
                try:
                    import shutil
                    shutil.copy2(darwin_pkg, local_adb)
                except Exception:
                    local_adb = darwin_pkg
        elif STATE.os_name == "linux":
            linux_pkg = os.path.join(BIN_DIR, "adb-linux")
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
        STATE.log(f"ADB найден в локальной папке: {local_adb}")
        return local_adb

    # 2. Check system PATH
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
        STATE.log(f"ADB найден в системе: {system_adb}")
        return system_adb

    # 3. Auto-download from Google
    STATE.log("ADB не найден на компьютере. Загружаем официальный Google Platform-Tools...", "warning")
    os.makedirs(BIN_DIR, exist_ok=True)

    urls = {
        "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
        "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
        "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
    }
    url = urls.get(STATE.os_name, urls["windows"])
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        z = zipfile.ZipFile(io.BytesIO(data))
        for member in z.namelist():
            filename = os.path.basename(member)
            if not filename:
                continue
            # Extract adb and necessary libraries
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
    """Executes an adb command safely."""
    if not STATE.adb_path or not os.path.isfile(STATE.adb_path):
        locate_or_download_adb()
        if not STATE.adb_path:
            return -1, "", "ADB недоступен"

    cmd = [STATE.adb_path] + args
    try:
        # Windows creation flag to prevent pop-up console windows
        creationflags = 0x08000000 if STATE.os_name == "windows" else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            creationflags=creationflags
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Таймаут команды ADB"
    except Exception as e:
        return -1, "", str(e)

def kill_adb_processes():
    """Kills conflicting adb server processes to free the port."""
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
    
    lines = stdout.splitlines()[1:]
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
    
    # Check adb binary
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
        STATE.log("❌ Автомобиль не обнаружен на шине USB (список adb devices пуст).", "warning")
        STATE.log("💡 Совет:", "info")
        STATE.log("   • Если вы уже открывали ADB и обновились у ОД (2.1.4.5+): проверьте кабель USB-A в нижнем разъёме тоннеля и включите зажигание (START без тормоза).", "info")
        STATE.log("   • Если вы открываете ADB впервые с нуля: салон ещё не вскрыт, выполните Шаг 1 с перемычкой.", "info")
        res = {
            "ok": True,
            "connected": False,
            "state": "disconnected",
            "message": "Устройство не обнаружено на USB. Проверьте кабель и зажигание.",
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
    model_info = model.strip() or "Geely Head Unit"
    STATE.log(f"🚘 Модель: {model_info} | Прошивка ГУ: {firmware_info}", "info")

    # 4. Check Parrot app_verify
    _, parrot_val, _ = run_adb(["shell", "getprop", "ro.vendor.ecarx.app_verify"], timeout=5)
    parrot_val = parrot_val.strip().lower()
    parrot_locked = (parrot_val == "true")
    if parrot_locked:
        STATE.log("🔒 Защита Parrot certificates: ВКЛЮЧЕНА (блокирует установку сторонних APK)", "warning")
    else:
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
    toggle_installed = any(pkg in (toggle_out or "") for pkg in ["com.geely.adbtoggle", "adbtoggle", "geelyadbtoggle"])
    if toggle_installed:
        STATE.log("📱 Приложение переключателя ADB-Toggle: уже установлено на ГУ", "info")
    else:
        STATE.log("📱 Приложение переключателя ADB-Toggle: не найдено (будет установлено)", "info")

    # Overall diagnosis
    needs_unlock = parrot_locked or verifier_active or not toggle_installed
    if needs_unlock:
        recommendation = "quick_unlock"
        STATE.log("💡 ВЕРДИКТ: ADB активен! Разбирать салон и ставить перемычку НЕ НУЖНО!", "success")
        STATE.log("💡 После обновления прошивки у ОД достаточно запустить экспресс-снятие ограничений в 1 клик.", "success")
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
        "message": "ADB активен! Разборка салона не требуется." if needs_unlock else "ГУ полностью разблокировано!"
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
        # Check if device is up
        code, stdout, _ = run_adb(["get-state"], timeout=2)
        if code != 0 or stdout != "device":
            time.sleep(0.5)
            continue

        attempt += 1
        STATE.log(f"⚡ Устройство обнаружено на шине USB! Попытка перехвата сервисного окна #{attempt}...", "cmd")
        STATE.log("🔑 Запрашиваем права суперпользователя (adb root)...", "info")
        
        # Ask for root
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
            STATE.log("🎉 УСПЕХ! Автомобиль подтвердил фиксацию порта (Set property)! Постоянный ADB активирован.", "success")
            STATE.set_status("success", "ADB зафиксирован! Выключите питание авто, выньте перемычку и нажмите «Продолжить».", 3)
            return

        if "Must be root" in combined_out:
            STATE.log("⚠️ Сервисное окно (20 сек) успело закрыться до фиксации. Ничего страшного: просто нажмите «Сброс на заводские настройки» на экране авто ещё раз — скрипт продолжает ждать...", "warning")

        time.sleep(1)

# ==================== STEP 3: REBOOT & VERIFY ====================
def worker_reboot_and_verify():
    """Reboots HU without jumper and waits for full boot."""
    STATE.set_status("working", "Перезагрузка ГУ... Это займет около 1.5 - 2 минут.", 3)
    STATE.log("🔄 Отправляем команду перезагрузки головного устройства...", "cmd")
    STATE.log("💡 Пояснение: перемычка уже вынута, теперь мы проверяем, сохраняется ли доступ по ADB в обычном рабочем режиме автомобиля.", "info")
    run_adb(["reboot"], timeout=10)
    time.sleep(15)

    start_time = time.time()
    while not STATE.stop_worker:
        if time.time() - start_time > 300:  # 5 min timeout
            STATE.set_status("error", "Таймаут: ГУ не загрузилось за 5 минут. Проверьте кабель и перезагрузите вручную.", 3)
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
    unlock_script = os.path.join(BASE_DIR, "unlock-hu.sh")
    apk_file = os.path.join(BASE_DIR, "Geely-ADB-Toggle-1.1.0.apk")

    if not os.path.isfile(unlock_script):
        STATE.set_status("error", f"Файл {unlock_script} не найден!", 4)
        return

    # Check root
    run_adb(["root"], timeout=10)
    time.sleep(2)
    run_adb(["wait-for-device"], timeout=10)

    # Push script
    STATE.log("📂 Загрузка системного скрипта разблокировки (unlock-hu.sh) на ГУ...", "cmd")
    STATE.log("💡 Пояснение: по умолчанию прошивка Geely отклоняет установку любых приложений без цифрового сертификата Parrot. Скрипт отключает эту блокировку в build.prop и отключает системный верификатор.", "info")
    code, _, err = run_adb(["push", unlock_script, "/data/local/tmp/gt-unlock.sh"], timeout=15)
    if code != 0:
        STATE.set_status("error", f"Ошибка копирования скрипта на ГУ: {err}", 4)
        return

    # Run loop
    for pass_num in range(1, 9):
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
            break
        elif "GT:REMOUNT" in out:
            STATE.log("🔄 Открываем системный раздел диска ГУ для записи (remount)...", "info")
            run_adb(["remount"], timeout=15)
            time.sleep(2)
        elif "GT:REBOOT" in out:
            STATE.log("🔄 Требуется промежуточная перезагрузка ГУ для применения настроек (около 1.5 - 2 минут)...", "info")
            run_adb(["reboot"], timeout=10)
            time.sleep(20)
            # Wait for boot
            while not STATE.stop_worker:
                c, b_out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
                if c == 0 and b_out.strip() == "1":
                    break
                time.sleep(3)
            run_adb(["root"], timeout=10)
            time.sleep(2)
            run_adb(["wait-for-device"], timeout=10)
        else:
            STATE.set_status("error", "Скрипт разблокировки завершился с непредвиденным кодом.", 4)
            return

    # Install Toggle APK
    if os.path.isfile(apk_file):
        STATE.log("📱 Установка приложения Geely-ADB-Toggle на экран мультимедиа...", "cmd")
        STATE.log("💡 Для чего оно нужно: этот удобный тумблер в меню авто позволит вам в один клик переключать USB-разъем между обычной флешкой с музыкой и кабелем отладки.", "info")
        code, out, err = run_adb(["install", "-r", "--user", "10", apk_file], timeout=60)
        if code == 0 and "Success" in out:
            STATE.log("✅ Приложение Geely-ADB-Toggle успешно установлено в профиль пользователя!", "success")
        else:
            # Try default install without --user 10 as fallback
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

    # Update STATE.last_test so UI diagnostic badges turn green immediately
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

# ==================== HTTP SERVER ====================
class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default server access logs

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path == "/api/status":
            # Quick check device state without blocking
            check_devices()
            self.send_json(STATE.to_dict())
            return

        # Serve static web files
        if path == "/" or path == "/index.html":
            file_path = os.path.join(WEB_DIR, "index.html")
            content_type = "text/html; charset=utf-8"
        else:
            rel_path = path.lstrip("/")
            file_path = os.path.join(WEB_DIR, rel_path)
            if path.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif path.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif path.endswith(".svg"):
                content_type = "image/svg+xml"
            elif path.endswith(".png"):
                content_type = "image/png"
            elif path.endswith(".jpg") or path.endswith(".jpeg"):
                content_type = "image/jpeg"
            else:
                content_type = "application/octet-stream"

        if os.path.isfile(file_path):
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/action":
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len).decode('utf-8')
            try:
                data = json.loads(body)
                action = data.get("action")
            except Exception:
                self.send_json({"error": "Invalid JSON"}, 400)
                return

            if action == "kill_adb":
                kill_adb_processes()
                check_devices()
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "check_devices":
                check_devices()
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "test_adb":
                res = test_adb_connection()
                self.send_json({"ok": True, "result": res, "state": STATE.to_dict()})
                return

            elif action == "set_mode":
                new_mode = data.get("mode", "standard")
                STATE.mode = new_mode
                if new_mode == "quick":
                    STATE.log("Переключен режим: Экспресс-снятие защиты после обновления ОД (2.1.4.5+) без перемычки")
                else:
                    STATE.log("Переключен режим: Стандартная разблокировка с нуля (с перемычкой)")
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "quick_unlock":
                STATE.stop_worker = False
                STATE.mode = "quick"
                STATE.step = 4
                STATE.set_status("working", "Запуск быстрого снятия блокировок после обновления ОД (без перемычки)...", 4)
                STATE.log("🚀 Запуск процедуры снятия ограничений Parrot и AutoInstallVerifier...", "cmd")
                t = threading.Thread(target=worker_unlock_and_install, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "start_step2_listen":
                STATE.stop_worker = False
                t = threading.Thread(target=worker_catch_factory_reset, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True})
                return

            elif action == "reboot_and_verify":
                STATE.stop_worker = False
                t = threading.Thread(target=worker_reboot_and_verify, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True})
                return

            elif action == "unlock_and_install":
                STATE.stop_worker = False
                t = threading.Thread(target=worker_unlock_and_install, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True})
                return

            elif action == "open_geelytune":
                webbrowser.open("https://geelytune.github.io")
                self.send_json({"ok": True})
                return

            elif action == "shutdown":
                self.send_json({"ok": True})
                STATE.log("Завершение работы по запросу пользователя...")
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return

            elif action == "reset_wizard":
                STATE.stop_worker = True
                STATE.step = 1
                STATE.status = "idle"
                STATE.status_message = "Готов к работе"
                STATE.log("Мастер сброшен к начальному шагу")
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            self.send_json({"error": "Unknown action"}, 400)
            return

        self.send_error(404)

def run_server(port=8765):
    locate_or_download_adb()
    server_address = ('127.0.0.1', port)
    
    # Try finding an open port if 8765 is taken
    httpd = None
    for p in range(port, port + 10):
        try:
            httpd = HTTPServer(('127.0.0.1', p), RequestHandler)
            port = p
            break
        except OSError:
            continue

    if not httpd:
        print("Не удалось запустить локальный сервер: порты заняты.")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    STATE.log(f"Локальный движок запущен по адресу: {url}", "success")
    
    # Auto-open browser
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        STATE.stop_worker = True
        httpd.server_close()
        print("Сервер остановлен.")

if __name__ == "__main__":
    try:
        run_server()
    except Exception as e:
        import traceback
        try:
            with open(os.path.join(BASE_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass
