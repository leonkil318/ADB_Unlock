#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Эмулятор аппаратного и системного состояния Головного Устройства (ГУ) Geely
(EX5, E5, Flyme Auto, Ecarx) для тестирования Geely ADB Unlock Master.

Реализует авторитарный встроенный IPC-сервер (127.0.0.1:динамический порт через .emulator_port):
Все команды от engine.py и demo_live.py приходят напрямую в эмулятор в реальном времени,
изменяют состояние памяти и мгновенно отображаются на экране ГУ.
"""

import sys
import os
import time
import json
import threading
import platform
import re
import socket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, ".emulator_state.json")
PORT_FILE = os.path.join(BASE_DIR, ".emulator_port")

# VT100 initialization for Windows
if platform.system() == "Windows":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
        kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        kernel32.SetConsoleTitleW("Эмулятор ГУ Geely (Стенд)")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Color codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"
C_BG_RED = "\033[41m"
C_BG_GREEN = "\033[42m"
C_BG_YELLOW = "\033[43m"
C_BG_BLUE = "\033[44m"

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def visible_len(s):
    """Calculates visible string length excluding ANSI escape codes."""
    return len(ANSI_RE.sub('', s))


def pad_line(content, width=78):
    """Pads string to exact visible width with spaces."""
    vlen = visible_len(content)
    pad = max(0, width - vlen)
    return content + (" " * pad)


def make_row(content):
    """Creates a perfectly aligned table row with border width 82."""
    return f"{C_BOLD}{C_CYAN}║{C_RESET} {pad_line(content, 78)} {C_BOLD}{C_CYAN}║{C_RESET}"



def setup_split_window(side="left"):
    """Positions console window for 50/50 split screen on Windows."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        r = (ctypes.c_long * 4)()
        # SPI_GETWORKAREA = 0x0030
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
        x_start = r[0]
        y_start = r[1]
        w_total = r[2] - r[0]
        h_total = r[3] - r[1]
        half_w = w_total // 2
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if side == "left":
            user32.MoveWindow(hwnd, x_start, y_start, half_w, h_total, True)
        else:
            user32.MoveWindow(hwnd, x_start + half_w, y_start, w_total - half_w, h_total, True)
    except Exception:
        pass


class HeadUnitEmulator:
    def __init__(self):
        self.lock = threading.RLock()
        self.running = True
        
        # Hardware link state
        self.cable_connected = False
        self.jumper_inserted = False
        
        # Firmware profile
        self.profile = "2.1.4.5"  # "early", "2.1.4.5", "2.2.0"
        self.window_duration = 13  # Seconds for factory reset window
        self.window_end = 0.0
        
        # System states
        self.vhal_unlocked = False  # VHAL 557872680 permanent ADB
        self.rebooting_until = 0.0
        self.parrot_disabled = False
        self.verifier_disabled = False
        self.toggle_installed = False
        self.toggle_active = True
        self.remounted_rw = False
        self.scratch_parked = False
        self.mark_remount = False
        self.gt_root_forced = False
        self.trusted_certs = []
        
        self.last_log = "Стенд инициализирован. Ожидание подключения..."
        self.log_history = [f"[{time.strftime('%H:%M:%S')}] Стенд ГУ готов к работе."]
        self.save_state()

    def get_dict(self):
        now = time.time()
        is_rebooting = now < self.rebooting_until
        in_reset_window = now < self.window_end
        
        adb_open = self.cable_connected and not is_rebooting and (
            (self.vhal_unlocked or (in_reset_window and self.jumper_inserted))
            and (not self.toggle_installed or self.toggle_active)
        )
        
        return {
            "active": True,
            "timestamp": now,
            "profile": self.profile,
            "cable_connected": self.cable_connected,
            "jumper_inserted": self.jumper_inserted,
            "window_duration": self.window_duration,
            "window_end": self.window_end,
            "window_remaining": max(0.0, self.window_end - now),
            "in_reset_window": in_reset_window,
            "adb_open": adb_open,
            "vhal_unlocked": self.vhal_unlocked,
            "is_rebooting": is_rebooting,
            "reboot_remaining": max(0.0, self.rebooting_until - now),
            "parrot_disabled": self.parrot_disabled,
            "verifier_disabled": self.verifier_disabled,
            "toggle_installed": self.toggle_installed,
            "toggle_active": self.toggle_active,
            "remounted_rw": self.remounted_rw,
            "scratch_parked": self.scratch_parked,
            "mark_remount": self.mark_remount,
            "gt_root_forced": self.gt_root_forced,
            "trusted_certs": self.trusted_certs,
            "last_log": self.last_log
        }

    def save_state(self):
        try:
            data = self.get_dict()
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def log(self, text):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {text}"
        self.last_log = entry
        self.log_history.append(entry)
        if len(self.log_history) > 15:
            self.log_history.pop(0)

    def trigger_factory_reset(self):
        with self.lock:
            now = time.time()
            if self.jumper_inserted:
                self.window_end = now + self.window_duration
                self.log(f"⚡ FACTORY RESET! Окно ADB открыто на {self.window_duration}с.")
            else:
                self.window_end = 0.0
                self.log("⚠️ FACTORY RESET: перемычки нет! Окно ADB не открылось.")
            self.save_state()

    def toggle_jumper(self):
        with self.lock:
            self.jumper_inserted = not self.jumper_inserted
            state_str = "УСТАНОВЛЕНА" if self.jumper_inserted else "ИЗВЛЕЧЕНА"
            self.log(f"Аппаратная перемычка: {state_str}")
            self.save_state()

    def toggle_cable(self):
        with self.lock:
            self.cable_connected = not self.cable_connected
            s = "ПОДКЛЮЧЕН" if self.cable_connected else "ОТКЛЮЧЕН"
            self.log(f"USB кабель: {s}")
            self.save_state()

    def set_profile(self, p):
        with self.lock:
            self.profile = p
            self.parrot_disabled = False
            self.verifier_disabled = False
            self.toggle_installed = False
            self.toggle_active = True
            self.remounted_rw = False
            self.scratch_parked = False
            self.mark_remount = False
            self.gt_root_forced = False
            self.trusted_certs = []
            self.log(f"Профиль прошивки изменен на: {self.get_profile_title()}")
            self.save_state()

    def reset_to_defaults(self):
        with self.lock:
            self.vhal_unlocked = False
            self.window_end = 0.0
            self.rebooting_until = 0.0
            self.parrot_disabled = False
            self.verifier_disabled = False
            self.toggle_installed = False
            self.toggle_active = True
            self.remounted_rw = False
            self.scratch_parked = False
            self.mark_remount = False
            self.gt_root_forced = False
            self.trusted_certs = []
            self.log("Состояние ГУ сброшено к заводскому (ADB закрыт, VHAL Locked).")
            self.save_state()


    def get_profile_title(self):
        if self.profile == "early":
            return "Ранняя ~2.1.3 (Маска T1.0.0, жесткий Parrot)"
        elif self.profile == "2.1.4.5":
            return "2.1.4.5+ (Маска T1.0.0, значки климата)"
        elif self.profile == "2.2.0":
            return "2.2.0 / GMC (Маска T1.0.0, лимит скорости)"
        return self.profile

    def handle_command(self, cmd_data):
        """Processes virtual ADB command received directly via IPC socket."""
        with self.lock:
            now = time.time()
            action = cmd_data.get("action")
            args = cmd_data.get("args", [])

            # Daemon control commands
            if action in ["start-server", "kill-server"]:
                return 0, "", ""

            # 1. Physical cable check
            if not self.cable_connected:
                if action == "devices":
                    return 0, "List of devices attached\n\n", ""
                return 1, "", "error: no devices/emulators found\n"

            # 2. Rebooting check
            if now < self.rebooting_until:
                if action == "devices":
                    return 0, "List of devices attached\nGEELY-EX5-EMULATOR\toffline\n", ""
                if action == "get-state":
                    return 1, "", "error: device offline\n"
                return -1, "", "error: device offline\n"

            # 3. ADB port status check
            in_window = (now < self.window_end and self.jumper_inserted)
            is_open = (self.vhal_unlocked or in_window)
            if self.toggle_installed and not self.toggle_active:
                is_open = False

            if action == "devices":
                if not is_open:
                    return 0, "List of devices attached\n\n", ""
                return 0, "List of devices attached\nGEELY-EX5-EMULATOR\tdevice\n", ""

            if action == "get-state":
                if not is_open:
                    return 1, "", "error: no devices/emulators found\n"
                return 0, "device\n", ""

            if not is_open:
                return 1, "", "error: device not found (ADB is closed)\n"

            # ADB is OPEN - process command
            if action == "root":
                if self.profile == "2.2.0" and not self.gt_root_forced:
                    return 1, "", "adbd cannot run as root in production builds\n"
                self.log("ADB ROOT: получен доступ суперпользователя (root)")
                self.save_state()
                return 0, "adbd is already running as root\n", ""

            if action == "wait-for-device":
                return 0, "", ""

            if action == "remount":
                self.remounted_rw = True
                self.log("ADB REMOUNT: разделы /product и /system переведены в RW")
                self.save_state()
                return 0, "remount succeeded\n", ""

            if action == "reboot":
                self.rebooting_until = now + 4.0  # 4 second reboot
                self.remounted_rw = False
                self.gt_root_forced = False
                self.log("ADB REBOOT: ГУ ушло в перезагрузку (4 сек)...")
                self.save_state()
                return 0, "", ""

            if action == "push":
                src = args[1] if len(args) > 1 else ""
                dest = args[2] if len(args) > 2 else ""
                self.log(f"ADB PUSH: {os.path.basename(src)} ➔ {dest}")
                self.save_state()
                return 0, f"1 file pushed: {dest}\n", ""

            if action == "install":
                apk = args[-1] if args else ""
                pkg = os.path.basename(apk)
                if "Geely-ADB-Toggle" in pkg:
                    self.toggle_installed = True
                    self.toggle_active = True
                    self.log(f"ADB INSTALL: Установлено приложение {pkg}")
                elif "parrot" in self.profile or self.parrot_disabled or self.profile == "2.2.0" or len(self.trusted_certs) > 0:
                    self.log(f"ADB INSTALL: Успешно установлен APK {pkg}")
                else:
                    return 1, "", "Failure [INSTALL_FAILED_VERIFICATION_FAILURE: failed to verify against Parrot certificates]\n"
                self.save_state()
                return 0, "Success\n", ""

            if action == "shell":
                cmd = " ".join(args[1:]) if len(args) > 1 else ""
                
                # Toggle commands
                if "persist.adb.enable 0" in cmd or "toggle_disable" in cmd:
                    self.toggle_active = False
                    self.log("ADB TOGGLE: Отладка по USB деактивирована через виджет")
                    self.save_state()
                    return 0, "ADB Disabled via Toggle\n", ""

                if "persist.adb.enable 1" in cmd or "toggle_enable" in cmd:
                    self.toggle_active = True
                    self.log("ADB TOGGLE: Отладка по USB активирована через виджет")
                    self.save_state()
                    return 0, "ADB Enabled via Toggle\n", ""

                # UID check
                if cmd == "id -u":
                    if self.profile == "2.2.0" and not self.gt_root_forced:
                        return 0, "2000\n", ""
                    return 0, "0\n", ""

                # Force gt_root
                if "service.adb.root 1" in cmd:
                    self.gt_root_forced = True
                    self.log("GT_ROOT: service.adb.root 1 активирован (пробит root для 2.2.0)")
                    self.save_state()
                    return 0, "\n", ""

                # Properties
                if cmd.startswith("getprop ro.product.model"):
                    return 0, "Geely EX5 EM-i\n", ""
                if cmd.startswith("getprop ro.build.display.id"):
                    if self.profile == "early":
                        return 0, "FlymeAuto-2.1.0-e245\n", ""
                    elif self.profile == "2.1.4.5":
                        return 0, "FlymeAuto-2.1.4.5-e245_eu\n", ""
                    return 0, "FlymeAuto-2.2.0-GMC-p145\n", ""

                if cmd.startswith("getprop ro.vendor.ecarx.app_verify"):
                    if self.profile == "early" or self.profile == "2.2.0":
                        return 0, "\n", ""
                    return 0, "false\n" if self.parrot_disabled else "true\n", ""

                if cmd.startswith("getprop ro.boot.veritymode"):
                    return 0, "enforcing\n" if self.profile == "2.2.0" else "disabled\n", ""

                if cmd.startswith("getprop sys.boot_completed"):
                    if now < self.rebooting_until:
                        return 0, "0\n", ""
                    return 0, "1\n", ""

                if "[ -d /system/etc/security/parrot ]" in cmd:
                    has_dir = self.profile in ["early", "2.1.4.5"]
                    return 0, "1\n" if has_dir else "0\n", ""

                # VHAL command
                if "557872680" in cmd:
                    if self.profile == "2.2.0" and not self.gt_root_forced:
                        return 1, "Must be root to access vehicle HAL\n", ""
                    if not self.jumper_inserted:
                        return 1, "VHAL: Jumper not detected, hardware strap missing\n", ""
                    self.vhal_unlocked = True
                    self.log("🎉 VHAL ПРИНЯТ: USB_SWITCH=0 (Постоянный ADB зафиксирован!)")
                    self.save_state()
                    return 0, "Set property: 557872680 to i: 0 a: 0\n", ""

                # Package list
                if "pm list packages -e" in cmd:
                    if self.verifier_disabled:
                        return 0, "\n", ""
                    return 0, "package:com.ecarx.xsfinstallverifier\n", ""

                if "pm list packages" in cmd:
                    pkgs = ["package:com.android.settings", "package:com.ecarx.system"]
                    if self.toggle_installed:
                        pkgs.append("package:com.yahooeu2k.ex5.adbtoggle")
                    return 0, "\n".join(pkgs) + "\n", ""

                if "pm disable-user" in cmd and "com.ecarx.xsfinstallverifier" in cmd:
                    self.verifier_disabled = True
                    self.log("PM DISABLE: AutoInstallVerifier успешно отключен")
                    self.save_state()
                    return 0, "Package com.ecarx.xsfinstallverifier new state: disabled-user\n", ""

                # Script unlock-hu.sh execution
                if "gt-unlock.sh" in cmd:
                    if "rescue" in cmd:
                        self.scratch_parked = True
                        self.log("GT-UNLOCK: Выполнен спасательный режим rescue (слой scratch отодвинут)")
                        self.save_state()
                        return 0, "GT:REBOOT\n", ""

                    self.verifier_disabled = True
                    if self.profile == "early":
                        self.log("GT-UNLOCK: Ранняя прошивка ➔ перенаправление на Parrot Trust")
                        self.save_state()
                        return 0, "Проверка подписи Parrot: на этой прошивке она включена всегда и выключателя не имеет\nGT:PARROT\n", ""

                    if self.profile == "2.1.4.5":
                        if not self.remounted_rw:
                            self.log("GT-UNLOCK: Отключение verifier, запрос remount системных разделов")
                            self.save_state()
                            return 0, "Проверяющий установок (AutoInstallVerifier): выключен\nПроверка подписи Parrot: включена, открываю системные разделы\nGT:REMOUNT\n", ""
                        else:
                            self.parrot_disabled = True
                            self.log("PARROT: Защита отключена в build.prop (app_verify=false)")
                            self.save_state()
                            return 0, "Проверка подписи Parrot: выключена в файле, нужна перезагрузка\nGT:REBOOT\n", ""

                    if self.profile == "2.2.0":
                        self.scratch_parked = True
                        if not self.mark_remount:
                            self.mark_remount = True
                            self.log("GT-UNLOCK 2.2.0: Оверлей scratch отодвинут, монтирование оверлея")
                            self.save_state()
                            return 0, "Проверяющий установок (AutoInstallVerifier): нет или уже выключен\nПроверка подписи Parrot: на этой прошивке её нет\nСлой прежней прошивки отодвинут в разделе scratch\nОткрываю системные разделы для нижней панели и медиамоста\nGT:REMOUNT\n", ""
                        else:
                            self.mark_remount = False
                            self.log("GT-UNLOCK 2.2.0: Системные слои успешно открыты")
                            self.save_state()
                            return 0, "Проверка подписи Parrot: на этой прошивке её нет\nGT:OK\n", ""

                # Parrot Trust mode commands
                if "/system/etc/security/parrot/" in cmd:
                    parts = cmd.split()
                    cert_name = [p for p in parts if ".pem" in p]
                    if cert_name:
                        self.trusted_certs.append(os.path.basename(cert_name[0]))
                        self.log(f"PARROT TRUST: Сертификат {os.path.basename(cert_name[0])} добавлен в систему")
                        self.save_state()
                    return 0, "\n", ""

                return 0, "\n", ""

            return 0, "\n", ""


_cleared_once = False


def render_ui(emu, is_watch=False):
    """Zero-flicker VT100 renderer with exact 82-column laser borders."""
    global _cleared_once
    if not _cleared_once:
        os.system("cls" if platform.system() == "Windows" else "clear")
        sys.stdout.write("\033[?25l")  # Hide console cursor
        _cleared_once = True

    d = emu.get_dict()
    
    # Firmware Profile
    p_name = emu.get_profile_title()

    # Cable Badge
    if d["cable_connected"]:
        cable_badge = f"{C_GREEN}🟢 ПОДКЛЮЧЕН (Линк USB 480 Мбит/с){C_RESET}"
    else:
        cable_badge = f"{C_RED}🔴 ОТКЛЮЧЕН (Нет физического линка){C_RESET}"

    # Jumper Badge
    if d["jumper_inserted"]:
        j_badge = f"{C_GREEN}🟢 УСТАНОВЛЕНА (Контакт 100%){C_RESET}"
    else:
        j_badge = f"{C_RED}🔴 ИЗВЛЕЧЕНА (Разомкнуто){C_RESET}"

    # ADB Status Badge
    if not d["cable_connected"]:
        adb_badge = f"{C_BG_RED}{C_WHITE} 🔴 НЕТ ЛИНКА (Кабель отключен) {C_RESET}"
    elif d["is_rebooting"]:
        adb_badge = f"{C_BG_BLUE}{C_WHITE} 🔄 ПЕРЕЗАГРУЗКА ({d['reboot_remaining']:.1f}с) {C_RESET}"
    elif not d["toggle_active"] and d["toggle_installed"]:
        adb_badge = f"{C_BG_YELLOW}{C_WHITE} ⏸️ ВЫКЛЮЧЕН ВИДЖЕТОМ (Скрыт для ТО) {C_RESET}"
    elif d["vhal_unlocked"]:
        adb_badge = f"{C_BG_GREEN}{C_WHITE} 🟢 ПОСТОЯННО ОТКРЫТ (VHAL UNLOCKED) {C_RESET}"
    elif d["in_reset_window"]:
        if d["jumper_inserted"]:
            adb_badge = f"{C_BG_YELLOW}{C_WHITE} ⚡ ОКНО СБРОСА: {d['window_remaining']:.1f} сек {C_RESET}"
        else:
            adb_badge = f"{C_BG_RED}{C_WHITE} 🔴 ПЕРЕМЫЧКА ОТСУТСТВУЕТ (ADB = 0) {C_RESET}"
    else:
        adb_badge = f"{C_BG_RED}{C_WHITE} 🔴 ЗАКРЫТ С ЗАВОДА (ADB OFF) {C_RESET}"

    # VHAL Status
    if d["vhal_unlocked"]:
        vhal_str = f"{C_GREEN}0 (USB_SWITCH=0, Unlocked Permanent){C_RESET}"
    else:
        vhal_str = f"{C_YELLOW}1 (USB_SWITCH=1, Factory Locked){C_RESET}"

    # Protections
    if emu.profile == "2.1.4.5":
        visual_cue = f"{C_YELLOW}Мини-значки климата внизу (обдув лобового){C_RESET}"
        p_stat = f"{C_GREEN}СНЯТА (app_verify=false){C_RESET}" if d["parrot_disabled"] else f"{C_RED}АКТИВНА (app_verify=true){C_RESET}"
        overlay_stat = f"{C_DIM}НЕ ТРЕБУЕТСЯ В 2.1.4{C_RESET}"
    elif emu.profile == "2.2.0":
        visual_cue = f"{C_YELLOW}Пункт «Лимит скорости» в меню ГУ (нет Parrot){C_RESET}"
        p_stat = f"{C_GREEN}ОТСУТСТВУЕТ В 2.2.0{C_RESET}"
        overlay_stat = f"{C_GREEN}ОБОЙДЕН (scratch-паркован){C_RESET}" if d["scratch_parked"] else f"{C_RED}АКТИВЕН (dm-verity RO){C_RESET}"
    else:  # early
        visual_cue = f"{C_YELLOW}Классический UI (нет лимита, Parrot в ядре){C_RESET}"
        p_stat = f"{C_GREEN}ОБОЙДЕНА (Parrot Trust инъекция){C_RESET}" if d["trusted_certs"] else f"{C_RED}ЖЕСТКАЯ (Вшита в ядро){C_RESET}"
        overlay_stat = f"{C_DIM}НЕ ТРЕБУЕТСЯ{C_RESET}"

    v_stat = f"{C_GREEN}ОТКЛЮЧЕН (com.ecarx...){C_RESET}" if d["verifier_disabled"] else f"{C_RED}АКТИВЕН (Блокирует сторонние APK){C_RESET}"
    
    if not d["toggle_installed"]:
        t_stat = f"{C_DIM}НЕ УСТАНОВЛЕН{C_RESET}"
    elif d["toggle_active"]:
        t_stat = f"{C_GREEN}УСТАНОВЛЕН (Отладка ВКЛ){C_RESET}"
    else:
        t_stat = f"{C_YELLOW}УСТАНОВЛЕН (Отладка ВЫКЛ, скрыт){C_RESET}"

    lines = [
        f"{C_BOLD}{C_CYAN}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}",
        f"{C_BOLD}{C_CYAN}║             ЭМУЛЯТОР ГОЛОВНОГО УСТРОЙСТВА GEELY (STAND HU)                     ║{C_RESET}",
        f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}",
        make_row(f"Прошивка:       {C_BOLD}{C_WHITE}{p_name}{C_RESET}"),
        make_row(f"Ориентир UI:    {visual_cue}"),
        make_row(f"Кабель USB:     {cable_badge}"),
        make_row(f"Перемычка:      {j_badge}"),
        make_row(f"Статус ADB:     {adb_badge}"),
        make_row(f"VHAL 557872680: {vhal_str}"),
        f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}",
        make_row(f"Защита Parrot:  {p_stat}"),
        make_row(f"Верификатор:    {v_stat}"),
        make_row(f"dm-verity / RO: {overlay_stat}"),
        make_row(f"ADB-Toggle APK: {t_stat}"),
        f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}",
    ]

    if is_watch:
        lines.append(make_row(f"{C_BOLD}{C_GREEN}📺 РЕЖИМ ЖИВОЙ ТРАНСЛЯЦИИ ДЛЯ СЪЕМКИ (Тест управляет стендом справа){C_RESET}"))
        lines.append(make_row("   Стенд обновляет состояние на лету при входящих ADB/VHAL командах..."))
    else:
        lines.append(make_row(f"УПРАВЛЕНИЕ: [R]=Сброс [J]=Перемычка [U]=Кабель [1-3]=Прошивка [Q]=Выход"))

    lines.append(f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    lines.append(make_row(f"{C_BOLD}ЖУРНАЛ СОБЫТИЙ БОРТОВОГО КОМПЬЮТЕРА:{C_RESET}"))
    
    last_logs = emu.log_history[-5:]
    for item in last_logs:
        lines.append(make_row(f" {C_DIM}{item}{C_RESET}"))
    for _ in range(5 - len(last_logs)):
        lines.append(make_row(""))
        
    lines.append(f"{C_BOLD}{C_CYAN}╚════════════════════════════════════════════════════════════════════════════════╝{C_RESET}")
    
    if not is_watch:
        lines.append(f"👉 Команда ({C_BOLD}R{C_RESET}=Сброс, {C_BOLD}J{C_RESET}=Перемычка, {C_BOLD}U{C_RESET}=Кабель, {C_BOLD}1-3{C_RESET}=Прошивка, {C_BOLD}Q{C_RESET}=Выход): ")

    # Atomic flicker-free flush
    buffer = "\033[H" + "\n".join(l + "\033[K" for l in lines) + "\n"
    sys.stdout.write(buffer)
    sys.stdout.flush()


def start_ipc_server(emu):
    """
    Direct Loopback Socket Server for real-time synchronization.
    Binds dynamically to an available port (15555..15575) avoiding TIME_WAIT,
    and publishes the port to .emulator_port.
    """
    server_sock = None
    for port in range(15555, 15575):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(10)
            server_sock = s
            with open(PORT_FILE, "w", encoding="utf-8") as f:
                f.write(str(port))
            break
        except Exception:
            continue

    if not server_sock:
        emu.log("IPC Server bind failed on all ports 15555..15575")
        return

    server_sock.settimeout(0.2)
    while emu.running:
        try:
            conn, _ = server_sock.accept()
        except socket.timeout:
            continue
        except Exception:
            break

        try:
            raw = b""
            while b"\n" not in raw:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                raw += chunk
                
            if not raw:
                conn.close()
                continue

            req = json.loads(raw.decode("utf-8").strip())

            # 1. Action command from demo_live
            if req.get("type") == "action":
                action = req.get("action")
                kwargs = req.get("kwargs", {})
                with emu.lock:
                    if action == "cable":
                        emu.cable_connected = kwargs.get("connected", True)
                        s_str = "ПОДКЛЮЧЕН" if emu.cable_connected else "ОТКЛЮЧЕН"
                        emu.log(f"USB кабель: {s_str}")
                    elif action == "jumper":
                        emu.jumper_inserted = kwargs.get("inserted", True)
                        s_str = "УСТАНОВЛЕНА" if emu.jumper_inserted else "ИЗВЛЕЧЕНА"
                        emu.log(f"Аппаратная перемычка: {s_str}")
                    elif action == "reset":
                        emu.trigger_factory_reset()
                    elif action == "profile":
                        emu.set_profile(kwargs.get("profile", "2.1.4.5"))
                    elif action == "reboot":
                        emu.rebooting_until = time.time() + kwargs.get("duration", 4.0)
                        emu.remounted_rw = False
                        emu.gt_root_forced = False
                        emu.log("REBOOT: ГУ выполняет перезагрузку...")
                    elif action == "toggle":
                        emu.toggle_active = kwargs.get("active", True)
                        s_str = "АКТИВИРОВАН (ADB ON)" if emu.toggle_active else "ОТКЛЮЧЕН (ADB OFF, скрыт для дилера)"
                        emu.log(f"Виджет ADB Toggle: {s_str}")
                    elif action == "restart_stand":
                        emu.reset_to_defaults()
                        emu.cable_connected = False
                        emu.jumper_inserted = False
                        emu.log("Стенд подготовлен к тесту (без кабеля, без перемычки)")

                emu.save_state()
                conn.sendall(json.dumps({"code": 0, "out": "OK", "err": ""}).encode("utf-8") + b"\n")
                conn.close()
                continue

            # 2. Standard ADB command from engine
            code, out, err = emu.handle_command(req)
            resp = {"code": code, "out": out, "err": err}
            conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    try:
        server_sock.close()
    except Exception:
        pass


def main():
    emu = HeadUnitEmulator()
    is_watch = "--watch" in sys.argv or "--demo" in sys.argv
    if is_watch or "--split" in sys.argv or "--side" in sys.argv:
        side = "right" if "--right" in sys.argv else "left"
        setup_split_window(side)
    
    def cleanup():
        emu.running = False
        sys.stdout.write("\033[?25h")  # Restore cursor
        sys.stdout.flush()
        try:
            if os.path.isfile(PORT_FILE):
                os.remove(PORT_FILE)
            if os.path.isfile(STATE_FILE):
                os.remove(STATE_FILE)
        except Exception:
            pass

    import atexit
    atexit.register(cleanup)

    # Start live IPC socket server
    t_ipc = threading.Thread(target=start_ipc_server, args=(emu,), daemon=True)
    t_ipc.start()

    if is_watch:
        try:
            while emu.running:
                render_ui(emu, is_watch=True)
                time.sleep(0.12)
        except KeyboardInterrupt:
            emu.running = False
    else:
        while emu.running:
            render_ui(emu, is_watch=False)
            try:
                cmd = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                break

            if cmd == "r":
                emu.trigger_factory_reset()
            elif cmd == "j":
                emu.toggle_jumper()
            elif cmd == "u":
                emu.toggle_cable()
            elif cmd == "1":
                emu.set_profile("early")
            elif cmd == "2":
                emu.set_profile("2.1.4.5")
            elif cmd == "3":
                emu.set_profile("2.2.0")
            elif cmd == "c":
                emu.reset_to_defaults()
            elif cmd == "q":
                emu.running = False
                break

    cleanup()
    print("\nЭмулятор остановлен. Файлы сессии удалены.")


if __name__ == "__main__":
    main()
