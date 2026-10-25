#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geely ADB Unlock Master — Simulation & Test Server (standalone test runner)
Does NOT modify or touch production core/ files or head unit.
Runs on port 8766.
"""

import os
import sys
import json
import time
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Windows console UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.dirname(SCRIPT_DIR)
WEB_DIR = os.path.join(CORE_DIR, "web")
SIM_PORT = 8766

class SimulationState:
    def __init__(self):
        self.lock = threading.Lock()
        self.step = 1
        self.status = "idle"
        self.status_message = "Симулятор запущен. Выберите сценарий тестирования."
        self.device_serial = None
        self.device_state = "disconnected"
        self.scenario = "success"  # "success", "window_retry", "remount_reboot", "timeout_error"
        self.logs = []
        self.stop_worker = False
        self.worker_thread = None

    def log(self, text, level="info"):
        timestamp = time.strftime("%H:%M:%S")
        prefix = {
            "info": "•",
            "success": "✓",
            "warning": "▲",
            "error": "✗",
            "cmd": "»"
        }.get(level, "•")
        entry = f"[{timestamp}] {prefix} {text}"
        with self.lock:
            self.logs.append({"time": timestamp, "text": text, "level": level, "formatted": entry})
            if len(self.logs) > 300:
                self.logs.pop(0)
        try:
            print(f"[TEST-SIM] {entry}")
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
                "os": sys.platform,
                "step": self.step,
                "status": self.status,
                "status_message": self.status_message,
                "adb_ready": True,
                "adb_path": "SIMULATED_ADB",
                "device_serial": self.device_serial or ("GEELY_EX5_SIM_001" if self.step > 1 else None),
                "device_state": self.device_state,
                "scenario": self.scenario,
                "is_simulation": True,
                "logs": self.logs[-50:]
            }

STATE = SimulationState()

# ==================== SIMULATION WORKERS ====================

def sim_worker_step2():
    """Simulates Step 2: factory reset window intercept with VHAL command."""
    scenario = STATE.scenario
    STATE.set_status("working", "[ТЕСТ] Ожидание перезагрузки ГУ после сброса на заводские настройки...", 2)
    STATE.log("[ТЕСТ СИМУЛЯЦИЯ] ВНИМАНИЕ: На экране автомобиля перейдите в «Настройки ➔ Система ➔ Сброс на заводские настройки» и подтвердите сброс.", "warning")
    STATE.log("💡 Как это работает: при штатном сбросе система кратковременно открывает 20-секундное окно отладки. Программа непрерывно сканирует USB-порт и автоматически перехватит его.", "info")

    time.sleep(2.5)
    if STATE.stop_worker: return

    # Scenario: Timeout error
    if scenario == "timeout_error":
        STATE.log("⏳ [ТЕСТ] Идёт сканирование шины USB... ГУ не обнаружено (прошло 10 сек).", "warning")
        time.sleep(3)
        STATE.set_status("error", "[ТЕСТ ОШИБКА] Таймаут: устройство не ответило на шине USB. Проверьте правильность подключения кабеля USB-A ↔ USB-A.", 2)
        return

    # Scenario: Missed 20-sec window retry
    if scenario == "window_retry":
        STATE.log("⚡ [ТЕСТ] Устройство обнаружено на шине USB! Попытка перехвата сервисного окна #1...", "cmd")
        time.sleep(1.2)
        STATE.log("🔑 [ТЕСТ] Запрашиваем права суперпользователя (adb root)...", "info")
        time.sleep(1.0)
        STATE.log("📡 [ТЕСТ] Отправка автомобилю VHAL-команды фиксации: USB_SWITCH=0...", "cmd")
        time.sleep(1.2)
        STATE.log("Ответ системы автомобиля: Must be root")
        STATE.log("⚠️ [ТЕСТ] Сервисное окно (20 сек) успело закрыться до фиксации. Ничего страшного: просто нажмите «Сброс на заводские настройки» на экране авто ещё раз — скрипт продолжает ждать...", "warning")
        time.sleep(3.5)
        if STATE.stop_worker: return
        STATE.log("⚡ [ТЕСТ] Повторное появление ГУ на шине USB! Попытка перехвата сервисного окна #2...", "cmd")
        time.sleep(1.2)

    # Standard success path
    STATE.log("⚡ [ТЕСТ] Устройство обнаружено на шине USB! Попытка перехвата сервисного окна...", "cmd")
    time.sleep(1.0)
    STATE.device_state = "connected"
    STATE.device_serial = "GEELY_EX5_SIM_001"
    STATE.log("🔑 [ТЕСТ] Запрашиваем права суперпользователя (adb root)...", "info")
    time.sleep(0.8)
    STATE.log("📡 [ТЕСТ] Отправка автомобилю VHAL-команды фиксации: USB_SWITCH=0 (постоянный ADB)...", "cmd")
    STATE.log("💡 Что делает команда: lshal записывает в системную шину автомобиля флаг постоянного режима ADB, чтобы он больше не выключался после перезагрузок.", "info")
    time.sleep(1.2)
    STATE.log("Ответ системы автомобиля: Set property 557872680 to (i 0, a 0)")
    STATE.log("🎉 [ТЕСТ] УСПЕХ! Автомобиль подтвердил фиксацию порта (Set property)! Постоянный ADB активирован.", "success")
    STATE.set_status("success", "ADB зафиксирован! Выключите питание авто, выньте перемычку и нажмите «Продолжить».", 3)

def sim_worker_step3():
    """Simulates Step 3: reboot and verify persistent connection."""
    scenario = STATE.scenario
    STATE.set_status("working", "[ТЕСТ] Перезагрузка ГУ... Имитация процесса загрузки Flyme Auto.", 3)
    STATE.log("🔄 [ТЕСТ] Отправляем команду перезагрузки головного устройства...", "cmd")
    STATE.log("💡 Пояснение: перемычка уже вынута, теперь мы проверяем, сохраняется ли доступ по ADB в обычном рабочем режиме автомобиля.", "info")
    STATE.device_state = "disconnected"
    
    time.sleep(2.0)
    if STATE.stop_worker: return

    if scenario == "timeout_error":
        time.sleep(3.0)
        STATE.set_status("error", "[ТЕСТ ОШИБКА] Таймаут: ГУ не подтвердило sys.boot_completed за отведенное время.", 3)
        return

    STATE.log("⏳ [ТЕСТ] Ожидание инициализации системных служб ГУ (sys.boot_completed)...", "info")
    time.sleep(2.5)
    if STATE.stop_worker: return

    STATE.log("✅ [ТЕСТ] Головное устройство полностью загрузилось! Проверяем постоянство связи ADB...", "success")
    time.sleep(1.0)
    STATE.device_state = "connected"
    STATE.log("🎉 [ТЕСТ] Связь подтверждена! ADB стабильно активен без перемычки.", "success")
    STATE.set_status("success", "ГУ перезагружено, ADB активен. Переходим к снятию системных ограничений.", 4)

def sim_worker_step4():
    """Simulates Step 4: unlock Parrot certificates and install toggle APK."""
    scenario = STATE.scenario
    STATE.set_status("working", "[ТЕСТ] Снятие ограничений установки и настройка системы...", 4)
    STATE.log("📂 [ТЕСТ] Загрузка системного скрипта разблокировки (unlock-hu.sh) на ГУ...", "cmd")
    STATE.log("💡 Пояснение: по умолчанию прошивка Geely отклоняет установку любых приложений без цифрового сертификата Parrot. Скрипт отключает эту блокировку в build.prop и отключает системный верификатор.", "info")
    time.sleep(1.5)
    if STATE.stop_worker: return

    if scenario == "remount_reboot":
        # Pass 1: Remount needed
        STATE.log("⚙️ [ТЕСТ] Выполнение процедур снятия защиты (проход 1/8)...", "cmd")
        time.sleep(1.2)
        STATE.log("🔄 [ТЕСТ] Открываем системный раздел диска ГУ для записи (remount)...", "info")
        time.sleep(1.5)
        # Pass 2: Reboot needed
        STATE.log("⚙️ [ТЕСТ] Выполнение процедур снятия защиты (проход 2/8)...", "cmd")
        time.sleep(1.2)
        STATE.log("🔄 [ТЕСТ] Требуется промежуточная перезагрузка ГУ для применения настроек в build.prop...", "info")
        time.sleep(2.5)
        STATE.log("✅ [ТЕСТ] ГУ перезагрузилось после настройки раздела.", "info")
        time.sleep(1.0)

    # Final pass
    STATE.log("⚙️ [ТЕСТ] Выполнение процедур снятия защиты (финальный проход)...", "cmd")
    time.sleep(1.5)
    STATE.log("Отключение com.ecarx.xsfinstallverifier...")
    STATE.log("Модификация ro.vendor.ecarx.app_verify=false...")
    STATE.log("GT:OK")
    STATE.log("✅ [ТЕСТ] Ограничения Parrot и системный верификатор успешно отключены!", "success")
    STATE.log("💡 Теперь система автомобиля позволит устанавливать любые стандартные Android APK (Яндекс.Навигатор, видеоплееры, лаунчеры).", "info")
    time.sleep(1.5)

    # APK Install
    STATE.log("📱 [ТЕСТ] Установка приложения Geely-ADB-Toggle на экран мультимедиа...", "cmd")
    STATE.log("💡 Для чего оно нужно: этот удобный тумблер в меню авто позволит вам в один клик переключать USB-разъем между обычной флешкой с музыкой и кабелем отладки.", "info")
    time.sleep(1.8)
    STATE.log("Success (установлено в профиль пользователя 10)")
    STATE.log("✅ [ТЕСТ] Приложение Geely-ADB-Toggle успешно установлено в профиль пользователя!", "success")
    time.sleep(1.0)

    # Post-unlock verification simulation
    STATE.log("[ТЕСТ] Проверка итогового статуса системы авто...", "cmd")
    STATE.log("🔓 [ТЕСТ] Защита Parrot certificates: ВЫКЛЮЧЕНА (false)", "success")
    STATE.log("🔓 [ТЕСТ] Системный верификатор AutoInstallVerifier: ОТКЛЮЧЕН", "success")

    # Update STATE.last_test to reflect that locks are removed
    if STATE.last_test and isinstance(STATE.last_test, dict):
        STATE.last_test["parrot_locked"] = False
        STATE.last_test["verifier_active"] = False
        STATE.last_test["toggle_installed"] = True
        STATE.last_test["needs_unlock"] = False
        STATE.last_test["recommendation"] = "ready"
        STATE.last_test["message"] = "ГУ полностью разблокировано!"
    else:
        STATE.last_test = {
            "ok": True,
            "connected": True,
            "serial": STATE.device_serial or "GEELY_EX5_TEST_883",
            "model": "Geely EX5 EM-i (Flyme Auto)",
            "firmware": "24.07.01.262972 (2.1.4.5+)",
            "root_ok": True,
            "parrot_locked": False,
            "verifier_active": False,
            "toggle_installed": True,
            "needs_unlock": False,
            "recommendation": "ready",
            "message": "ГУ полностью разблокировано!"
        }

    STATE.set_status("success", "Поздравляем! Разблокировка полностью завершена!", 5)
    STATE.log("🏆 [ТЕСТ] ВСЕ ЭТАПЫ РАЗБЛОКИРОВКИ ВЫПОЛНЕНЫ! Теперь вы можете устанавливать любые приложения через официальный веб-установщик GeelyTune.", "success")

# ==================== HTTP HANDLER ====================

class SimRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
            self.send_json(STATE.to_dict())
            return

        # Serve web page with test toolbar injected
        if path == "/" or path == "/index.html":
            file_path = os.path.join(WEB_DIR, "index.html")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    html = f.read()

                # Simulation toolbar injection
                sim_bar = """
                <!-- SIMULATION TEST TOOLBAR -->
                <div style="background: linear-gradient(90deg, #1e1b4b, #0f172a); border-bottom: 2px solid #818cf8; padding: 8px 16px; display: flex; align-items: center; justify-content: space-between; font-family: sans-serif; font-size: 13px; z-index: 9999;">
                  <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: #4f46e5; color: #fff; font-weight: 700; padding: 3px 8px; border-radius: 4px; font-size: 11px; letter-spacing: 0.05em;">🧪 РЕЖИМ ТЕСТА / СИМУЛЯЦИИ</span>
                    <span style="color: #cbd5e1;">Выберите сценарий проверки:</span>
                    <select id="sim-scenario-select" style="background: #0f172a; color: #38bdf8; border: 1px solid #38bdf8; border-radius: 4px; padding: 4px 8px; font-size: 12px; font-weight: 600; cursor: pointer;">
                      <option value="success">1. Идеальный ход (Успех 100%)</option>
                      <option value="window_retry">2. Опоздали в окно 20 сек (Must be root -> повтор)</option>
                      <option value="remount_reboot">3. Снятие защиты с перезагрузкой (Remount / Reboot)</option>
                      <option value="timeout_error">4. Ошибка связи / Таймаут USB</option>
                    </select>
                  </div>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #94a3b8; font-size: 11.5px;">(Реальное ГУ и файлы системы не затрагиваются)</span>
                    <button id="sim-btn-restart" style="background: #334155; color: #fff; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; padding: 4px 10px; font-size: 12px; cursor: pointer;">Перезапустить тест</button>
                  </div>
                </div>
                <script>
                  document.addEventListener('DOMContentLoaded', () => {
                    const sel = document.getElementById('sim-scenario-select');
                    const btn = document.getElementById('sim-btn-restart');
                    if (sel) {
                      sel.addEventListener('change', async () => {
                        await fetch('/api/action', {
                          method: 'POST',
                          headers: {'Content-Type': 'application/json'},
                          body: JSON.stringify({ action: 'set_scenario', scenario: sel.value })
                        });
                      });
                    }
                    if (btn) {
                      btn.addEventListener('click', async () => {
                        await fetch('/api/action', {
                          method: 'POST',
                          headers: {'Content-Type': 'application/json'},
                          body: JSON.stringify({ action: 'reset_wizard' })
                        });
                        if (typeof updateStepper === 'function') updateStepper(1);
                      });
                    }
                  });
                </script>
                """

                # Inject after <body> tag
                if "<body>" in html:
                    html = html.replace("<body>", "<body>\n" + sim_bar)

                body = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as e:
                self.send_error(500, str(e))
                return

        # Serve other static files from web/
        rel_path = path.lstrip("/")
        file_path = os.path.join(WEB_DIR, rel_path)
        if os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

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

            if action == "set_scenario":
                STATE.scenario = data.get("scenario", "success")
                STATE.log(f"[ТЕСТ] Выбран сценарий тестирования: {STATE.scenario}", "info")
                self.send_json({"ok": True, "scenario": STATE.scenario})
                return

            elif action == "test_adb":
                STATE.log("[ТЕСТ] Имитация проверки связи с автомобилем (Тест ADB)...", "cmd")
                time.sleep(0.8)
                is_connected = STATE.scenario != "timeout_error"
                res = {
                    "ok": True,
                    "connected": is_connected,
                    "serial": "GEELY_EX5_TEST_883" if is_connected else None,
                    "model": "Geely EX5 EM-i (Flyme Auto)" if is_connected else None,
                    "firmware": "24.07.01.262972 (2.1.4.5+)" if is_connected else None,
                    "root_ok": is_connected,
                    "parrot_locked": is_connected,
                    "verifier_active": is_connected,
                    "toggle_installed": False,
                    "needs_unlock": is_connected,
                    "recommendation": "quick_unlock" if is_connected else "not_connected",
                    "message": "ADB активен! Разборка салона не требуется." if is_connected else "Устройство не обнаружено."
                }
                if is_connected:
                    STATE.device_state = "connected"
                    STATE.device_serial = "GEELY_EX5_TEST_883"
                    STATE.log("✅ [ТЕСТ] Автомобиль подключен: Geely EX5 EM-i | Прошивка: 24.07.01.262972 (2.1.4.5+)", "success")
                    STATE.log("🔒 [ТЕСТ] Защита Parrot certificates: ВКЛЮЧЕНА (блокирует сторонние APK)", "warning")
                    STATE.log("💡 [ТЕСТ] ВЕРДИКТ: ADB активен! Разбирать салон не нужно, достаточно экспресс-снятия блокировок.", "success")
                else:
                    STATE.device_state = "disconnected"
                    STATE.device_serial = None
                    STATE.log("❌ [ТЕСТ] Устройство не обнаружено по ADB.", "warning")
                self.send_json({"ok": True, "result": res, "state": STATE.to_dict()})
                return

            elif action == "set_mode":
                mode = data.get("mode", "standard")
                STATE.log(f"[ТЕСТ] Режим переключен на: {mode}", "info")
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "quick_unlock":
                STATE.stop_worker = False
                STATE.step = 4
                STATE.set_status("working", "[ТЕСТ] Экспресс-снятие блокировок после обновления ОД...", 4)
                STATE.log("🚀 [ТЕСТ] Запуск скрипта снятия Parrot и AutoInstallVerifier...", "cmd")
                t = threading.Thread(target=sim_worker_step4, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "start_step2_listen":
                STATE.stop_worker = False
                t = threading.Thread(target=sim_worker_step2, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True})
                return

            elif action == "reboot_and_verify":
                STATE.stop_worker = False
                t = threading.Thread(target=sim_worker_step3, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True})
                return

            elif action == "unlock_and_install":
                STATE.stop_worker = False
                t = threading.Thread(target=sim_worker_step4, daemon=True)
                STATE.worker_thread = t
                t.start()
                self.send_json({"ok": True})
                return

            elif action == "open_geelytune":
                STATE.log("[ТЕСТ] Имитация перехода на официальный сайт GeelyTune...", "success")
                webbrowser.open("https://geelytune.github.io")
                self.send_json({"ok": True})
                return

            elif action == "reset_wizard":
                STATE.stop_worker = True
                STATE.step = 1
                STATE.status = "idle"
                STATE.status_message = "Симулятор сброшен. Выберите сценарий тестирования."
                STATE.device_state = "disconnected"
                STATE.log("[ТЕСТ] Симулятор сброшен в исходное состояние (Шаг 1).", "info")
                self.send_json({"ok": True, "state": STATE.to_dict()})
                return

            elif action == "shutdown":
                STATE.log("[ТЕСТ] Завершение работы симулятора по запросу...")
                self.send_json({"ok": True})
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return

            self.send_json({"ok": True})
            return

        self.send_error(404)

def run_sim_server():
    print("=" * 60)
    print("  Geely ADB Unlock Master — ТЕСТОВЫЙ СИМУЛЯТОР РАЗБЛОКИРОВКИ")
    print(f"  Порт: http://127.0.0.1:{SIM_PORT}")
    print("  Режимы: 1. Успех | 2. Окно 20с (Must be root) | 3. Remount/Reboot | 4. Ошибка")
    print("=" * 60)
    
    server = HTTPServer(("127.0.0.1", SIM_PORT), SimRequestHandler)
    
    # Auto open browser
    def open_browser():
        time.sleep(1.0)
        webbrowser.open(f"http://127.0.0.1:{SIM_PORT}")
        
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ТЕСТ] Остановка сервера симуляции...")
    finally:
        server.server_close()

if __name__ == "__main__":
    run_sim_server()
