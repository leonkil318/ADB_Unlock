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
        self.step = 1  # 1: Preparation, 2: Factory Reset & VHAL, 3: Jumper removal & Reboot, 4: Unlock Parrot & Toggle, 5: Finished
        self.status = "idle"  # idle, working, waiting_reset, success, error
        self.status_message = "Готов к работе"
        self.device_serial = None
        self.device_state = "disconnected"
        self.logs = []
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
                "step": self.step,
                "status": self.status,
                "status_message": self.status_message,
                "adb_ready": self.adb_ready,
                "adb_path": self.adb_path,
                "device_serial": self.device_serial,
                "device_state": self.device_state,
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

# ==================== STEP 2: FACTORY RESET CATCH ====================
def worker_catch_factory_reset():
    """Continuously waits for device reboot, grants root, and sets VHAL property."""
    STATE.set_status("working", "Ожидание перезагрузки ГУ после сброса настроек... Не закрывайте окно!", 2)
    STATE.log("ВНИМАНИЕ: Сделайте сброс до заводских настроек на экране автомобиля сейчас!", "warning")
    STATE.log("Скрипт циклически опрашивает порт и перехватит 20-секундное окно root...", "info")

    vhal_cmd = "/system/bin/lshal debug android.hardware.automotive.vehicle@2.0::IVehicle/default --set 557872680 i 0 a 0"
    attempt = 0

    while not STATE.stop_worker:
        # Check if device is up
        code, stdout, _ = run_adb(["get-state"], timeout=2)
        if code != 0 or stdout != "device":
            time.sleep(0.5)
            continue

        attempt += 1
        STATE.log(f"Устройство обнаружено на шине USB! Попытка перехвата #{attempt}...", "cmd")
        
        # Ask for root
        run_adb(["root"], timeout=5)
        time.sleep(0.5)
        run_adb(["wait-for-device"], timeout=5)
        run_adb(["remount"], timeout=5)

        STATE.log("Отправка VHAL-команды фиксации ADB...", "cmd")
        code, out, err = run_adb(["shell", vhal_cmd], timeout=8)
        combined_out = f"{out} {err}".strip()
        STATE.log(f"Ответ VHAL: {combined_out}")

        if "Set property" in combined_out:
            STATE.log("УСПЕХ! Порт ADB успешно зафиксирован на постоянной основе!", "success")
            STATE.set_status("success", "ADB зафиксирован! Выньте перемычку и нажмите «Продолжить».", 3)
            return

        if "Must be root" in combined_out:
            STATE.log("Окно root (20 сек) было упущено. Запустите сброс до заводских настроек ещё раз, скрипт продолжает ждать...", "warning")

        time.sleep(1)

# ==================== STEP 3: REBOOT & VERIFY ====================
def worker_reboot_and_verify():
    """Reboots HU without jumper and waits for full boot."""
    STATE.set_status("working", "Перезагрузка ГУ... Это займет около 1.5 - 2 минут.", 3)
    STATE.log("Отправляем команду перезагрузки ГУ...", "cmd")
    run_adb(["reboot"], timeout=10)
    time.sleep(15)

    start_time = time.time()
    while not STATE.stop_worker:
        if time.time() - start_time > 300:  # 5 min timeout
            STATE.set_status("error", "Таймаут: ГУ не загрузилось за 5 минут. Проверьте кабель и перезагрузите вручную.", 3)
            return

        code, out, _ = run_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
        if code == 0 and out.strip() == "1":
            STATE.log("ГУ успешно загрузилось! Проверяем постоянство ADB...", "success")
            time.sleep(2)
            check_devices()
            if STATE.device_state == "connected":
                STATE.log("ADB стабильно активен без перемычки!", "success")
                STATE.set_status("success", "ГУ перезагружено, ADB активен. Переходим к снятию блокировок.", 4)
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
    STATE.log("Загрузка скрипта разблокировки на ГУ...", "cmd")
    code, _, err = run_adb(["push", unlock_script, "/data/local/tmp/gt-unlock.sh"], timeout=15)
    if code != 0:
        STATE.set_status("error", f"Ошибка копирования скрипта на ГУ: {err}", 4)
        return

    # Run loop
    for pass_num in range(1, 9):
        STATE.log(f"Выполнение скрипта разблокировки (проход {pass_num}/8)...", "cmd")
        code, out, _ = run_adb(["shell", "sh", "/data/local/tmp/gt-unlock.sh"], timeout=60)
        
        for line in out.splitlines():
            line_str = line.strip()
            if line_str and not line_str.startswith("GT:"):
                STATE.log(line_str)

        if "GT:OK" in out:
            run_adb(["shell", "rm", "-f", "/data/local/tmp/gt-unlock.sh"], timeout=5)
            STATE.log("Блокировки Parrot и верификатор приложений успешно отключены!", "success")
            break
        elif "GT:REMOUNT" in out:
            STATE.log("Требуется перемонтирование разделов, выполняем remount...", "info")
            run_adb(["remount"], timeout=15)
            time.sleep(2)
        elif "GT:REBOOT" in out:
            STATE.log("Требуется промежуточная перезагрузка ГУ (около 2 минут)...", "info")
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
        STATE.log("Установка приложения ADB Toggle (переключатель ADB на экране)...", "cmd")
        code, out, err = run_adb(["install", "-r", "--user", "10", apk_file], timeout=60)
        if code == 0 and "Success" in out:
            STATE.log("Приложение Geely-ADB-Toggle успешно установлено!", "success")
        else:
            # Try default install without --user 10 as fallback
            STATE.log(f"Установка в пользователя 10 вернула: {out} {err}. Пробуем обычную установку...", "warning")
            code2, out2, _ = run_adb(["install", "-r", apk_file], timeout=60)
            if "Success" in out2:
                STATE.log("Приложение Geely-ADB-Toggle успешно установлено!", "success")
            else:
                STATE.log(f"Предупреждение при установке APK: {out2}", "warning")
    else:
        STATE.log("APK-файл переключателя не найден в папке core, пропускаем установку переключателя", "warning")

    STATE.set_status("success", "Поздравляем! Разблокировка полностью завершена!", 5)
    STATE.log("ВСЕ ЭТАПЫ ВЫПОЛНЕНЫ! Теперь вы можете установить любые приложения через GeelyTune.", "success")

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
