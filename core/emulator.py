#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Эмулятор аппаратного и системного состояния Головного Устройства (ГУ) Geely
(EX5, E5, Flyme Auto, Ecarx) для тестирования Geely ADB Unlock Master.

Поддерживает 3 профиля прошивок:
1) Ранняя прошивка (< 2.1.4) — жесткий Parrot (/system/etc/security/parrot)
2) 2.1.4.5 / 2.1.4.6 — Parrot в build.prop, AutoInstallVerifier, VHAL 557872680
3) 2.2.0 / GMC — без Parrot, dm-verity, scratch-оверлеи, gt_root loop
"""

import sys
import os
import time
import json
import threading
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, ".emulator_state.json")

# VT100 initialization for Windows
if platform.system() == "Windows":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
        kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
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
C_BG_BLUE = "\033[44m"


class HeadUnitEmulator:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = True
        
        # Default state
        self.profile = "2.1.4.5"  # "early", "2.1.4.5", "2.2.0"
        self.jumper_inserted = True
        self.window_duration = 13  # Seconds for factory reset window
        self.window_end = 0.0
        
        self.vhal_unlocked = False  # VHAL 557872680 permanent ADB
        self.rebooting_until = 0.0
        
        # System states
        self.parrot_disabled = False
        self.verifier_disabled = False
        self.toggle_installed = False
        self.remounted_rw = False
        self.scratch_parked = False
        self.mark_remount = False
        self.gt_root_forced = False
        self.trusted_certs = []
        
        self.last_log = "Эмулятор запущен. Ожидание команд..."
        self.log_history = []
        self.save_state()

    def get_dict(self):
        now = time.time()
        is_rebooting = now < self.rebooting_until
        in_reset_window = now < self.window_end
        
        # ADB is open if VHAL is unlocked OR (in reset window AND jumper is inserted)
        adb_open = not is_rebooting and (self.vhal_unlocked or (in_reset_window and self.jumper_inserted))
        
        return {
            "active": True,
            "timestamp": now,
            "profile": self.profile,
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
        if len(self.log_history) > 10:
            self.log_history.pop(0)

    def trigger_factory_reset(self):
        with self.lock:
            now = time.time()
            if self.jumper_inserted:
                self.window_end = now + self.window_duration
                self.log(f"⚡ FACTORY RESET! Сервисное окно ADB открыто на {self.window_duration} секунд.")
            else:
                self.window_end = 0.0
                self.log("⚠️ FACTORY RESET: перемычка НЕ установлена! Сервисное окно не открылось (ADB = 0).")
            self.save_state()

    def toggle_jumper(self):
        with self.lock:
            self.jumper_inserted = not self.jumper_inserted
            state_str = "УСТАНОВЛЕНА" if self.jumper_inserted else "ИЗВЛЕЧЕНА"
            self.log(f"Аппаратная перемычка: {state_str}")
            self.save_state()

    def set_profile(self, p):
        with self.lock:
            self.profile = p
            # Reset internal flags
            self.parrot_disabled = False
            self.verifier_disabled = False
            self.toggle_installed = False
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
            self.remounted_rw = False
            self.scratch_parked = False
            self.mark_remount = False
            self.gt_root_forced = False
            self.trusted_certs = []
            self.log("Состояние ГУ сброшено к заводскому (ADB закрыт, VHAL заблокирован).")
            self.save_state()

    def get_profile_title(self):
        if self.profile == "early":
            return "Ранняя (< 2.1.4, жесткий Parrot в /system)"
        elif self.profile == "2.1.4.5":
            return "2.1.4.5 / 2.1.4.6 (Parrot в build.prop, Verifier)"
        elif self.profile == "2.2.0":
            return "2.2.0 / GMC (Без Parrot, verity, scratch, gt_root)"
        return self.profile

    def handle_command(self, cmd_data):
        """Processes virtual ADB command received from engine."""
        with self.lock:
            now = time.time()
            action = cmd_data.get("action")
            args = cmd_data.get("args", [])

            # Check if rebooting
            if now < self.rebooting_until and action != "get-state":
                return -1, "", "device offline"

            # Check if ADB is open
            is_open = self.vhal_unlocked or (now < self.window_end and self.jumper_inserted)

            if action == "devices":
                if not is_open:
                    return 0, "List of devices attached\n", ""
                return 0, "List of devices attached\nGEELY-EX5-EMULATOR\tdevice\n", ""

            if action == "get-state":
                if now < self.rebooting_until:
                    return 1, "", "error: device offline"
                if not is_open:
                    return 1, "", "error: no devices/emulators found"
                return 0, "device", ""

            if not is_open:
                return 1, "", "error: device not found (ADB is closed)"

            # ADB is OPEN - handle commands
            if action == "root":
                if self.profile == "2.2.0" and not self.gt_root_forced:
                    return 1, "", "adbd cannot run as root in production builds"
                return 0, "adbd is already running as root", ""

            if action == "wait-for-device":
                return 0, "", ""

            if action == "remount":
                self.remounted_rw = True
                self.log("ADB REMOUNT: разделы /product и /system переведены в RW")
                self.save_state()
                return 0, "remount succeeded", ""

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
                return 0, f"1 file pushed: {dest}", ""

            if action == "install":
                apk = args[-1] if args else ""
                pkg = os.path.basename(apk)
                if "Geely-ADB-Toggle" in pkg:
                    self.toggle_installed = True
                    self.log(f"ADB INSTALL: Установлено приложение {pkg}")
                elif "parrot" in self.profile or self.parrot_disabled or self.profile == "2.2.0":
                    self.log(f"ADB INSTALL: Успешно установлен APK {pkg}")
                else:
                    return 1, "", "Failure [INSTALL_FAILED_VERIFICATION_FAILURE: failed to verify against Parrot certificates]"
                self.save_state()
                return 0, "Success", ""

            if action == "shell":
                cmd = " ".join(args[1:]) if len(args) > 1 else ""
                
                # UID check
                if cmd == "id -u":
                    if self.profile == "2.2.0" and not self.gt_root_forced:
                        return 0, "2000", ""
                    return 0, "0", ""

                # Force gt_root
                if "service.adb.root 1" in cmd:
                    self.gt_root_forced = True
                    self.log("GT_ROOT: активирован service.adb.root 1 (пробит root для 2.2.0)")
                    self.save_state()
                    return 0, "", ""

                # Properties
                if cmd.startswith("getprop ro.product.model"):
                    return 0, "Geely EX5 EM-i", ""
                if cmd.startswith("getprop ro.build.display.id"):
                    if self.profile == "early":
                        return 0, "FlymeAuto-2.1.0-e245", ""
                    elif self.profile == "2.1.4.5":
                        return 0, "FlymeAuto-2.1.4.5-e245_eu", ""
                    return 0, "FlymeAuto-2.2.0-GMC-p145", ""

                if cmd.startswith("getprop ro.vendor.ecarx.app_verify"):
                    if self.profile == "early" or self.profile == "2.2.0":
                        return 0, "", ""
                    return 0, "false" if self.parrot_disabled else "true", ""

                if cmd.startswith("getprop ro.boot.veritymode"):
                    return 0, "enforcing" if self.profile == "2.2.0" else "disabled", ""

                if cmd.startswith("getprop sys.boot_completed"):
                    if now < self.rebooting_until:
                        return 0, "0", ""
                    return 0, "1", ""

                if "[ -d /system/etc/security/parrot ]" in cmd:
                    has_dir = self.profile in ["early", "2.1.4.5"]
                    return 0, "1" if has_dir else "0", ""

                # VHAL command
                if "557872680" in cmd:
                    if self.profile == "2.2.0" and not self.gt_root_forced:
                        return 1, "Must be root to access vehicle HAL", ""
                    if not self.jumper_inserted:
                        return 1, "VHAL: Jumper not detected, hardware strap missing", ""
                    self.vhal_unlocked = True
                    self.log("🎉 VHAL ПРИНЯТ: USB_SWITCH=0 (Постоянный ADB зафиксирован!)")
                    self.save_state()
                    return 0, "Set property: 557872680 to i: 0 a: 0", ""

                # Package list
                if "pm list packages -e" in cmd:
                    if self.verifier_disabled:
                        return 0, "", ""
                    return 0, "package:com.ecarx.xsfinstallverifier", ""

                if "pm list packages" in cmd:
                    pkgs = ["package:com.android.settings", "package:com.ecarx.system"]
                    if self.toggle_installed:
                        pkgs.append("package:com.yahooeu2k.ex5.adbtoggle")
                    return 0, "\n".join(pkgs), ""

                if "pm disable-user" in cmd and "com.ecarx.xsfinstallverifier" in cmd:
                    self.verifier_disabled = True
                    self.log("PM DISABLE: AutoInstallVerifier успешно отключен")
                    self.save_state()
                    return 0, "Package com.ecarx.xsfinstallverifier new state: disabled-user", ""

                # Script unlock-hu.sh execution
                if "gt-unlock.sh" in cmd:
                    if "rescue" in cmd:
                        self.scratch_parked = True
                        self.log("GT-UNLOCK: Выполнен спасательный режим rescue (слой scratch отодвинут)")
                        self.save_state()
                        return 0, "GT:REBOOT", ""

                    self.verifier_disabled = True
                    if self.profile == "early":
                        return 0, "Проверка подписи Parrot: на этой прошивке она включена всегда и выключателя не имеет\nGT:PARROT", ""

                    if self.profile == "2.1.4.5":
                        if not self.remounted_rw:
                            return 0, "Проверяющий установок (AutoInstallVerifier): выключен\nПроверка подписи Parrot: включена, открываю системные разделы\nGT:REMOUNT", ""
                        else:
                            self.parrot_disabled = True
                            self.save_state()
                            return 0, "Проверка подписи Parrot: выключена в файле, нужна перезагрузка\nGT:REBOOT", ""

                    if self.profile == "2.2.0":
                        self.scratch_parked = True
                        if not self.mark_remount:
                            self.mark_remount = True
                            self.save_state()
                            return 0, "Проверяющий установок (AutoInstallVerifier): нет или уже выключен\nПроверка подписи Parrot: на этой прошивке её нет\nСлой прежней прошивки отодвинут в разделе scratch\nОткрываю системные разделы для нижней панели и медиамоста\nGT:REMOUNT", ""
                        else:
                            self.mark_remount = False
                            self.save_state()
                            return 0, "Проверка подписи Parrot: на этой прошивке её нет\nGT:OK", ""

                # Parrot Trust mode commands
                if "/system/etc/security/parrot/" in cmd:
                    parts = cmd.split()
                    cert_name = [p for p in parts if ".pem" in p]
                    if cert_name:
                        self.trusted_certs.append(os.path.basename(cert_name[0]))
                        self.log(f"PARROT TRUST: Сертификат {os.path.basename(cert_name[0])} добавлен в систему")
                        self.save_state()
                    return 0, "", ""

                return 0, "", ""

            return 0, "", ""


def render_ui(emu):
    os.system("cls" if platform.system() == "Windows" else "clear")
    d = emu.get_dict()
    
    # Header
    print(f"{C_BOLD}{C_CYAN}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║             ЭМУЛЯТОР ГОЛОВНОГО УСТРОЙСТВА GEELY (STAND HU)                     ║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    
    # Firmware Profile
    p_name = emu.get_profile_title()
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} Прошивка:      {C_BOLD}{C_WHITE}{p_name:<64}{C_RESET} {C_BOLD}{C_CYAN}║{C_RESET}")
    
    # ADB Status
    if d["is_rebooting"]:
        adb_badge = f"{C_BG_BLUE}{C_WHITE} 🔄 ПЕРЕЗАГРУЗКА ({d['reboot_remaining']:.1f}с) {C_RESET}"
    elif d["vhal_unlocked"]:
        adb_badge = f"{C_BG_GREEN}{C_WHITE} 🟢 ПОСТОЯННО ОТКРЫТ (VHAL UNLOCKED) {C_RESET}"
    elif d["in_reset_window"]:
        if d["jumper_inserted"]:
            adb_badge = f"{C_BG_YELLOW}{C_WHITE} ⚡ ОКНО СБРОСА: {d['window_remaining']:.1f} сек {C_RESET}"
        else:
            adb_badge = f"{C_BG_RED}{C_WHITE} 🔴 ПЕРЕМЫЧКА ОТСУТСТВУЕТ (ADB = 0) {C_RESET}"
    else:
        adb_badge = f"{C_BG_RED}{C_WHITE} 🔴 ЗАКРЫТ (ADB OFF) {C_RESET}"

    print(f"{C_BOLD}{C_CYAN}║{C_RESET} Статус ADB:    {adb_badge:<73} {C_BOLD}{C_CYAN}║{C_RESET}")
    
    # Jumper
    j_badge = f"{C_GREEN}🟢 УСТАНОВЛЕНА (Контакт 100%){C_RESET}" if d["jumper_inserted"] else f"{C_RED}🔴 ИЗВЛЕЧЕНА (Разомкнуто){C_RESET}"
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} Перемычка:     {j_badge:<73} {C_BOLD}{C_CYAN}║{C_RESET}")
    
    # VHAL Status
    vhal_str = f"{C_GREEN}0 (USB_SWITCH=0, Unlocked){C_RESET}" if d["vhal_unlocked"] else f"{C_YELLOW}1 (USB_SWITCH=1, Locked){C_RESET}"
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} VHAL 557872680: {vhal_str:<73} {C_BOLD}{C_CYAN}║{C_RESET}")
    
    # Security protections
    p_stat = f"{C_GREEN}СНЯТА (app_verify=false){C_RESET}" if d["parrot_disabled"] else (f"{C_RED}ВКЛЮЧЕНА (app_verify=true){C_RESET}" if emu.profile == "2.1.4.5" else (f"{C_RED}ЖЕСТКАЯ (Вшита в систему){C_RESET}" if emu.profile == "early" else f"{C_GREEN}ОТСУТСТВУЕТ В 2.2.0{C_RESET}"))
    v_stat = f"{C_GREEN}ОТКЛЮЧЕН{C_RESET}" if d["verifier_disabled"] else f"{C_RED}АКТИВЕН{C_RESET}"
    t_stat = f"{C_GREEN}УСТАНОВЛЕН{C_RESET}" if d["toggle_installed"] else f"{C_DIM}НЕ УСТАНОВЛЕН{C_RESET}"
    
    print(f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} Защита Parrot: {p_stat:<73} {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} Верификатор:   {v_stat:<73} {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} ADB-Toggle:    {t_stat:<73} {C_BOLD}{C_CYAN}║{C_RESET}")
    
    # Actions
    print(f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} УПРАВЛЕНИЕ:                                                                     {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[R]{C_RESET} Нажать «Сброс настроек» (Factory Reset) ➔ открыть окно ADB на {d['window_duration']}с       {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[J]{C_RESET} Вставить / Извлечь перемычку                                             {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[1]{C_RESET} Выбрать прошивку 1: Ранняя (< 2.1.4, жесткий Parrot)                      {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[2]{C_RESET} Выбрать прошивку 2: 2.1.4.5 / 2.1.4.6 (Parrot в build.prop, Verifier)    {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[3]{C_RESET} Выбрать прошивку 3: 2.2.0 / GMC (Без Parrot, scratch, gt_root)           {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[C]{C_RESET} Полный сброс состояния стенда к заводскому                              {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_BOLD}[Q]{C_RESET} Выход из эмулятора                                                       {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}║{C_RESET} ЖУРНАЛ СОБЫТИЙ:                                                                 {C_BOLD}{C_CYAN}║{C_RESET}")
    for item in emu.log_history[-4:]:
        print(f"{C_BOLD}{C_CYAN}║{C_RESET}  {C_DIM}{item:<77}{C_RESET} {C_BOLD}{C_CYAN}║{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}╚════════════════════════════════════════════════════════════════════════════════╝{C_RESET}")
    print(f"👉 Введите команду ({C_BOLD}R{C_RESET}=Сброс, {C_BOLD}J{C_RESET}=Перемычка, {C_BOLD}1-3{C_RESET}=Прошивка, {C_BOLD}Q{C_RESET}=Выход) и нажмите Enter: ", end="", flush=True)


def background_updater(emu):
    """Refreshes state file and screen timer, syncing external updates from engine."""
    while emu.running:
        try:
            if os.path.isfile(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with emu.lock:
                    if data.get("vhal_unlocked") and not emu.vhal_unlocked:
                        emu.vhal_unlocked = True
                        emu.log("🎉 VHAL ПРИНЯТ: USB_SWITCH=0 (Постоянный ADB успешно зафиксирован!)")
                    if data.get("parrot_disabled") and not emu.parrot_disabled:
                        emu.parrot_disabled = True
                        emu.log("PARROT: Защита отключена в build.prop (app_verify=false)")
                    if data.get("verifier_disabled") and not emu.verifier_disabled:
                        emu.verifier_disabled = True
                    if data.get("toggle_installed") and not emu.toggle_installed:
                        emu.toggle_installed = True
                        emu.log("APK: Приложение Geely-ADB-Toggle успешно установлено")
                    if data.get("scratch_parked") and not emu.scratch_parked:
                        emu.scratch_parked = True
                        emu.log("SCRATCH: Оверлей прежней прошивки отодвинут (2.2.0)")
                    if data.get("rebooting_until", 0) > emu.rebooting_until:
                        emu.rebooting_until = data.get("rebooting_until")
                        emu.log("REBOOT: ГУ выполняет перезагрузку...")
        except Exception:
            pass
        emu.save_state()
        time.sleep(0.3)


def main():
    emu = HeadUnitEmulator()
    
    # Clean on exit
    def cleanup():
        try:
            if os.path.isfile(STATE_FILE):
                os.remove(STATE_FILE)
        except Exception:
            pass

    import atexit
    atexit.register(cleanup)

    t = threading.Thread(target=background_updater, args=(emu,), daemon=True)
    t.start()

    while emu.running:
        render_ui(emu)
        try:
            cmd = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "r":
            emu.trigger_factory_reset()
        elif cmd == "j":
            emu.toggle_jumper()
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
    print("\nЭмулятор остановлен. Файл состояния удален.")


if __name__ == "__main__":
    main()
