"""
Geely ADB Unlock Master - Zero-Dependency TUI / CLI Interface
Old-school hacker / patcher terminal style with pure ANSI escape codes.
Features dynamic terminal width detection and responsive word-wrapping.
Works out of the box on Windows (cmd/PowerShell/Windows Terminal), macOS, and Linux.
"""

import sys
import os
import time
import re
import shutil
import textwrap
import threading
import unicodedata
from sound import play_sound, is_sound_enabled

# Terminal color and style definitions
C_RESET   = "\033[0m"
C_BOLD    = "\033[1m"
C_DIM     = "\033[2m"
C_CYAN    = "\033[96;1m"
C_GREEN   = "\033[92;1m"
C_YELLOW  = "\033[93;1m"
C_RED     = "\033[91;1m"
C_WHITE   = "\033[97;1m"
C_GRAY    = "\033[90m"

ANSI_REGEX = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def get_char_width(c):
    """Returns visual terminal cell width of a character (0, 1, or 2)."""
    if c in ('\ufe0e', '\ufe0f') or unicodedata.combining(c):
        return 0
    w = unicodedata.east_asian_width(c)
    if w in ('F', 'W'):
        return 2
    return 1


def visible_len(s):
    """Calculates visible display cell width of a string ignoring ANSI color codes."""
    clean = ANSI_REGEX.sub('', s)
    return sum(get_char_width(c) for c in clean)


def get_terminal_width():
    """Returns dynamic terminal width matching the actual console window."""
    cols = 0
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hOut = kernel32.CreateFileW("CONOUT$", 0x80000000 | 0x40000000, 3, None, 3, 0, None)
            if hOut != -1:
                class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                    _fields_ = [
                        ('dwSize_X', ctypes.c_short), ('dwSize_Y', ctypes.c_short),
                        ('dwCursorPosition_X', ctypes.c_short), ('dwCursorPosition_Y', ctypes.c_short),
                        ('wAttributes', ctypes.c_ushort),
                        ('srWindow_Left', ctypes.c_short), ('srWindow_Top', ctypes.c_short),
                        ('srWindow_Right', ctypes.c_short), ('srWindow_Bottom', ctypes.c_short),
                        ('dwMaximumWindowSize_X', ctypes.c_short), ('dwMaximumWindowSize_Y', ctypes.c_short),
                    ]
                csbi = CONSOLE_SCREEN_BUFFER_INFO()
                if kernel32.GetConsoleScreenBufferInfo(hOut, ctypes.byref(csbi)):
                    cols = csbi.srWindow_Right - csbi.srWindow_Left + 1
                kernel32.CloseHandle(hOut)
        except Exception:
            pass
    if not cols:
        cols = shutil.get_terminal_size(fallback=(100, 24)).columns
    return max(65, min(cols - 2, 130))


def pad_box_line(text, inner_width):
    """Pads text with spaces so it precisely fills the inner box width in display cells."""
    vlen = visible_len(text)
    if vlen > inner_width:
        clean = ""
        cur = 0
        for ch in ANSI_REGEX.sub('', text):
            cw = get_char_width(ch)
            if cur + cw > inner_width:
                break
            clean += ch
            cur += cw
        return clean + (" " * (inner_width - cur))
    return text + (" " * (inner_width - vlen))


def init_terminal():
    """Initializes terminal encoding, enables ANSI processing, and maximizes window on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32

            # 1. Maximize console window (SW_MAXIMIZE = 3) so all text, tables and UI fit cleanly
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 3)
                time.sleep(0.08)
            else:
                os.system("mode con: cols=120 lines=42 >nul 2>&1")

            # 2. Enable virtual terminal processing (VT100 / ANSI colors)
            hOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(hOut, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(hOut, mode.value | 0x0004)
        except Exception:
            pass

    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def clear_screen():
    """Clears the terminal screen smoothly."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def print_banner(W=None):
    """Renders the cyan hacker-style header banner adaptively to window width."""
    if W is None:
        W = get_terminal_width()
    inner = W - 2

    top = f"{C_CYAN}╔" + ("═" * inner) + f"╗{C_RESET}"
    bot = f"{C_CYAN}╚" + ("═" * inner) + f"╝{C_RESET}"

    t1 = "GEELY ADB UNLOCK MASTER"
    t2 = "Flyme Auto / Ecarx Service Terminal • EX5 EM-i / X80 / Universal"

    def center_line(text, color):
        v = visible_len(text)
        left = max(0, (inner - v) // 2)
        right = max(0, inner - v - left)
        return f"{C_CYAN}║{C_RESET}{' ' * left}{color}{text}{C_RESET}{' ' * right}{C_CYAN}║{C_RESET}"

    print(top)
    print(center_line(t1, C_WHITE))
    print(center_line(t2, C_GRAY))
    print(bot)


def render_diagnostic_card(state):
    """Renders the live diagnostic status card adaptively."""
    W = get_terminal_width()
    inner = W - 4

    t = state.last_test
    has_test = bool(t)
    t = t or {}

    connected = t.get("connected", state.device_state == "connected")
    serial = t.get("serial") or state.device_serial or "Не обнаружено"
    model = t.get("model") or ("Штатное ГУ Geely" if connected else "-")
    os_info = t.get("os_info") or t.get("firmware") or ("ОС Android" if connected else "-")

    if connected:
        adb_badge = f"{C_GREEN}[ АКТИВЕН ]{C_RESET}"
    elif t.get("state") == "unauthorized":
        adb_badge = f"{C_YELLOW}[ ТРЕБУЕТ ДОПУСК ]{C_RESET}"
    else:
        adb_badge = f"{C_RED}[ НЕ ПОДКЛЮЧЕН ]{C_RESET}"

    if connected and has_test:
        p_desc = t.get("parrot_status_desc")
        if t.get("parrot_locked"):
            if p_desc == "hardcoded":
                parrot_badge = f"{C_RED}[ ВШИТА (СТАРАЯ) ]{C_RESET}"
            else:
                parrot_badge = f"{C_YELLOW}[ БЛОКИРУЕТ ]{C_RESET}"
        elif p_desc == "absent":
            parrot_badge = f"{C_GREEN}[ ОТСУТСТВУЕТ ]{C_RESET}"
        elif p_desc == "disabled":
            parrot_badge = f"{C_GREEN}[ ВЫКЛЮЧЕНА ]{C_RESET}"
        else:
            parrot_badge = f"{C_GREEN}[ СНЯТА ]{C_RESET}"

        if t.get("verifier_active"):
            verifier_badge = f"{C_YELLOW}[ АКТИВЕН ]{C_RESET}"
        else:
            verifier_badge = f"{C_GREEN}[ ОТКЛЮЧЕН ]{C_RESET}"
    elif connected:
        parrot_badge = f"{C_GRAY}[ НЕ ПРОВЕРЕНО ]{C_RESET}"
        verifier_badge = f"{C_GRAY}[ НЕ ПРОВЕРЕНО ]{C_RESET}"
        os_info = f"{C_GRAY}Нажмите [3] для теста{C_RESET}"
    else:
        parrot_badge = f"{C_GRAY}[ - ]{C_RESET}"
        verifier_badge = f"{C_GRAY}[ - ]{C_RESET}"

    emu_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".emulator_state.json")
    emu_info = ""
    if os.path.isfile(emu_file):
        try:
            with open(emu_file, "r", encoding="utf-8") as f:
                ed = json.load(f)
            if ed.get("active") and time.time() - ed.get("timestamp", 0) < 15.0:
                emu_info = f"🧪 СТЕНД-ЭМУЛЯТОР: {ed.get('profile', '')}"
        except Exception:
            pass

    if emu_info:
        title_str = f"┌─ СТАТУС ({emu_info}) "
    else:
        title_str = "┌─ СТАТУС ПОДКЛЮЧЕНИЯ И ДИАГНОСТИКА "
    dash_count = max(2, W - visible_len(title_str) - 1)
    print(f"{C_CYAN}{title_str}{'─' * dash_count}┐{C_RESET}")

    if W >= 74:
        # Two-column layout
        half = inner // 2
        col1_w = half
        col2_w = inner - half

        l1_c1 = f"Связь ADB:     {adb_badge}"
        l1_c2 = f"Серийник:    {C_WHITE}{serial}{C_RESET}"
        pad1 = " " * max(0, col1_w - visible_len(l1_c1))
        pad2 = " " * max(0, col2_w - visible_len(l1_c2))
        print(f"{C_CYAN}│{C_RESET} {l1_c1}{pad1}{l1_c2}{pad2} {C_CYAN}│{C_RESET}")

        l2_c1 = f"Модель ГУ:     {C_WHITE}{model}{C_RESET}"
        l2_c2 = f"ОС ГУ:       {C_CYAN}{os_info}{C_RESET}"
        pad1 = " " * max(0, col1_w - visible_len(l2_c1))
        pad2 = " " * max(0, col2_w - visible_len(l2_c2))
        print(f"{C_CYAN}│{C_RESET} {l2_c1}{pad1}{l2_c2}{pad2} {C_CYAN}│{C_RESET}")

        l3_c1 = f"Защита Parrot: {parrot_badge}"
        l3_c2 = f"Верификатор: {verifier_badge}"
        pad1 = " " * max(0, col1_w - visible_len(l3_c1))
        pad2 = " " * max(0, col2_w - visible_len(l3_c2))
        print(f"{C_CYAN}│{C_RESET} {l3_c1}{pad1}{l3_c2}{pad2} {C_CYAN}│{C_RESET}")
    else:
        # Stacked layout for compact terminal
        def print_single(text):
            p = pad_box_line(text, inner)
            print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")

        print_single(f"Связь ADB:     {adb_badge}")
        print_single(f"Серийник:      {C_WHITE}{serial}{C_RESET}")
        print_single(f"Модель ГУ:     {C_WHITE}{model}{C_RESET}")
        print_single(f"ОС ГУ:         {C_CYAN}{os_info}{C_RESET}")
        print_single(f"Защита Parrot: {parrot_badge}")
        print_single(f"Верификатор:   {verifier_badge}")

    print(f"{C_CYAN}└{'─' * (W - 2)}┘{C_RESET}")


def render_menu(state):
    """Renders the action menu adaptively."""
    W = get_terminal_width()
    inner = W - 4

    t = state.last_test or {}
    connected = t.get("connected", state.device_state == "connected")
    needs_unlock = t.get("needs_unlock", True)

    title_str = "┌─ МЕНЮ ДЕЙСТВИЙ "
    dash_count = max(2, W - visible_len(title_str) - 1)
    print(f"{C_CYAN}{title_str}{'─' * dash_count}┐{C_RESET}")

    def print_menu_item(text):
        p = pad_box_line(text, inner)
        print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")

    if connected and needs_unlock:
        print_menu_item(f"{C_GREEN}{C_BOLD}[1] Снять защиту установки (Универсально: любая версия под T1.0.0){C_RESET}")
    else:
        print_menu_item(f"{C_WHITE}[1]{C_RESET} Снять защиту установки (Универсально: любая версия под T1.0.0)")

    print_menu_item(f"{C_WHITE}[2]{C_RESET} Открыть ADB с нуля (Фиксация порта через перемычку + сброс ГУ)")
    print_menu_item(f"{C_WHITE}[3]{C_RESET} Проверить статус ГУ (Диагностика связи и состояния блокировок)")
    print_menu_item(f"{C_GREEN}{C_BOLD}[4] Открыть GeelyTune в браузере (твики и помощник ГУ){C_RESET}")
    print_menu_item(f"{C_WHITE}[5]{C_RESET} Открыть магазин EX5 Apps (установка софта через браузер от @wingus)")
    print_menu_item(f"{C_WHITE}[6]{C_RESET} Перезапустить службу ADB (Очистить зависшие процессы)")
    sound_badge = f"{C_GREEN}[ ВКЛ ]{C_RESET}" if is_sound_enabled() else f"{C_GRAY}[ ВЫКЛ ]{C_RESET}"
    print_menu_item(f"{C_WHITE}[7]{C_RESET} Звуковые эффекты: {sound_badge}")
    print_menu_item(f"{C_YELLOW}[8]{C_RESET} Справка: Что делает программа? (Простыми словами)")
    if t.get("parrot_status_desc") == "hardcoded":
        print_menu_item(f"{C_YELLOW}{C_BOLD}[T] Установить APK через Parrot Trust (для ранней прошивки < 2.1.4.5){C_RESET}")
    else:
        print_menu_item(f"{C_GRAY}[T] Установить APK через Parrot Trust (только для ранних прошивок < 2.1.4.5){C_RESET}")
    print_menu_item(f"{C_GRAY}[0] Выход{C_RESET}")

    print(f"{C_CYAN}└{'─' * (W - 2)}┘{C_RESET}")


def render_recent_logs(state, count=5):
    """Prints recent log entries with responsive multi-line word-wrapping."""
    W = get_terminal_width()
    inner = W - 4

    title_str = "┌─ ЖУРНАЛ СООБЩЕНИЙ "
    dash_count = max(2, W - visible_len(title_str) - 1)
    print(f"{C_CYAN}{title_str}{'─' * dash_count}┐{C_RESET}")

    recent = state.logs[-count:] if state.logs else []
    if not recent:
        p = pad_box_line(f"{C_GRAY}Журнал пуст. Выберите действие в меню выше.{C_RESET}", inner)
        print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")
    else:
        for entry in recent:
            level = entry.get("level", "info")
            color = {
                "cmd": C_CYAN,
                "success": C_GREEN,
                "warning": C_YELLOW,
                "error": C_RED,
                "info": C_WHITE
            }.get(level, C_WHITE)
            
            raw_text = entry.get("formatted", entry.get("text", ""))
            clean_text = ANSI_REGEX.sub('', raw_text)

            # Responsive word wrapping inside box
            wrapped_lines = textwrap.wrap(clean_text, width=inner, subsequent_indent="   ")
            for sub_line in wrapped_lines:
                colored_sub = f"{color}{sub_line}{C_RESET}"
                p = pad_box_line(colored_sub, inner)
                print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")

    print(f"{C_CYAN}└{'─' * (W - 2)}┘{C_RESET}")


def print_error_card(err):
    """Renders a structured, clear diagnostic error card with actionable advice."""
    W = get_terminal_width()
    inner = W - 4

    title_str = "┌─ ДИАГНОСТИКА И ПРИЧИНА СБОЯ "
    dash_count = max(2, W - visible_len(title_str) - 1)
    print(f"\n{C_RED}{title_str}{'─' * dash_count}┐{C_RESET}")

    def print_line(styled_text):
        p = pad_box_line(styled_text, inner)
        print(f"{C_RED}│{C_RESET} {p} {C_RED}│{C_RESET}")

    def print_empty():
        print(f"{C_RED}│{C_RESET} {' ' * inner} {C_RED}│{C_RESET}")

    # Title
    title = err.get("title", "Сбой выполнения операции")
    print_line(f"{C_RED}{C_BOLD}[!] СБОЙ: {title}{C_RESET}")
    print(f"{C_RED}├{'─' * (W - 2)}┤{C_RESET}")

    # Reason
    reason = err.get("reason", "")
    if reason:
        print_line(f"{C_YELLOW}{C_BOLD}• Суть проблемы:{C_RESET}")
        for r_line in textwrap.wrap(reason, width=inner - 4):
            print_line(f"  {r_line}")
        print_empty()

    # Steps
    steps = err.get("steps", [])
    if steps:
        print_line(f"{C_CYAN}{C_BOLD}• Рекомендуемые действия:{C_RESET}")
        for i, step in enumerate(steps, 1):
            wrapped = textwrap.wrap(f"{i}. {step}", width=inner - 4, subsequent_indent="   ")
            for s_line in wrapped:
                print_line(f"  {s_line}")
        print_empty()

    # Technical ADB details (if available and different from title)
    raw = err.get("raw", "")
    if raw and raw.strip() != title.strip():
        print_line(f"{C_GRAY}{C_BOLD}• Исходный код ошибки системы (ADB):{C_RESET}")
        clean_raw = ANSI_REGEX.sub('', str(raw)).strip()
        for raw_line in clean_raw.splitlines()[:3]:
            for w_r in textwrap.wrap(raw_line, width=inner - 4):
                print_line(f"  {C_GRAY}{w_r}{C_RESET}")

    print(f"{C_RED}└{'─' * (W - 2)}┘{C_RESET}")


def run_interactive_task(state, task_fn, title="Выполнение операции"):
    """Runs a background task while streaming live logs and an animated spinner adaptively."""
    clear_screen()
    print_banner()
    W = get_terminal_width()

    print(f"\n{C_CYAN}{C_BOLD}[*] {title.upper()}{C_RESET}")
    print(f"{C_GRAY}Нажмите Ctrl+C для прерывания в случае необходимости.{C_RESET}\n")

    state.stop_worker = False
    state.status = "running"
    state.last_error_details = None
    worker_finished = threading.Event()
    play_sound("step")

    def runner():
        try:
            task_fn()
        except Exception as e:
            state.log(f"Исключение в процессе: {e}", "error")
        finally:
            worker_finished.set()

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    spinner_frames = ["-", "\\", "|", "/"]
    idx = 0
    last_log_count = len(state.logs)

    try:
        while not worker_finished.is_set():
            # Check for new logs
            current_len = len(state.logs)
            if current_len > last_log_count:
                # Clear active spinner line before printing logs
                if sys.stdout.isatty():
                    sys.stdout.write("\r" + (" " * (W + 2)) + "\r")
                    sys.stdout.flush()
                for entry in state.logs[last_log_count:current_len]:
                    lvl = entry.get("level", "info")
                    col = {
                        "cmd": C_CYAN,
                        "success": C_GREEN,
                        "warning": C_YELLOW,
                        "error": C_RED,
                        "info": C_WHITE
                    }.get(lvl, C_WHITE)

                    raw_text = entry.get('formatted', entry.get('text', ''))
                    clean_text = ANSI_REGEX.sub('', raw_text)
                    for wrapped_line in textwrap.wrap(clean_text, width=max(40, W - 4), subsequent_indent="   "):
                        print(f" {col}{wrapped_line}{C_RESET}")
                last_log_count = current_len

            if sys.stdout.isatty():
                frame = spinner_frames[idx % len(spinner_frames)]
                status_text = state.status_message[:max(10, W - 14)]
                spinner_line = f" {C_CYAN}[{frame}]{C_RESET} {C_GRAY}{status_text}{C_RESET}"
                padding = " " * max(0, W - 2 - visible_len(spinner_line))
                sys.stdout.write(f"\r{spinner_line}{padding}\r")
                sys.stdout.flush()

            # Soft, musical sonar progress beacon every ~2.5 seconds (25 ticks * 0.1s)
            if idx > 0 and idx % 25 == 0:
                play_sound("radar")

            idx += 1
            time.sleep(0.1)

        # Clear spinner line completely
        if sys.stdout.isatty():
            sys.stdout.write("\r" + (" " * (W + 2)) + "\r")
            sys.stdout.flush()

        # Print remaining logs
        current_len = len(state.logs)
        if current_len > last_log_count:
            for entry in state.logs[last_log_count:current_len]:
                lvl = entry.get("level", "info")
                col = {
                    "cmd": C_CYAN,
                    "success": C_GREEN,
                    "warning": C_YELLOW,
                    "error": C_RED,
                    "info": C_WHITE
                }.get(lvl, C_WHITE)

                raw_text = entry.get('formatted', entry.get('text', ''))
                clean_text = ANSI_REGEX.sub('', raw_text)
                for wrapped_line in textwrap.wrap(clean_text, width=max(40, W - 4), subsequent_indent="   "):
                    print(f" {col}{wrapped_line}{C_RESET}")

        if state.status == "success":
            play_sound("success")
            print(f"\n{C_GREEN}{C_BOLD}[OK] ОПЕРАЦИЯ УСПЕШНО ЗАВЕРШЕНА!{C_RESET}")
        elif state.status == "error":
            play_sound("error")
            err = getattr(state, "last_error_details", None)
            if err:
                print_error_card(err)
            else:
                title = state.status_message
                print(f"\n{C_RED}{C_BOLD}[!] ПРОИЗОШЛА ОШИБКА: {title}{C_RESET}")

    except KeyboardInterrupt:
        state.stop_worker = True
        play_sound("step")
        print(f"\n\n{C_YELLOW}[!] Операция прервана пользователем.{C_RESET}")

    print()
    try:
        input(f"{C_CYAN}Нажмите Enter для возврата в меню...{C_RESET}")
    except (KeyboardInterrupt, EOFError):
        pass


def render_help_screen():
    """Renders a friendly, easy-to-understand explanation of what the program does with the car."""
    clear_screen()
    print_banner()
    W = get_terminal_width()
    inner = W - 4

    def box_title(title):
        t = f"┌─ {title} "
        dash = max(2, W - visible_len(t) - 1)
        print(f"\n{C_CYAN}{t}{'─' * dash}┐{C_RESET}")

    def box_line(text, color=C_WHITE):
        clean = ANSI_REGEX.sub('', text)
        for line in textwrap.wrap(clean, width=inner, subsequent_indent="  "):
            p = pad_box_line(f"{color}{line}{C_RESET}", inner)
            print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")

    def box_bottom():
        print(f"{C_CYAN}└{'─' * (W - 2)}┘{C_RESET}")

    box_title("[1] СУТЬ ПРОГРАММЫ: ЧТО МЫ ДЕЛАЕМ С МАШИНОЙ?")
    box_line("Экран мультимедиа Geely — это обычный Android-планшет. Но с завода он", C_WHITE)
    box_line("заперт в «бронированный сейф»:", C_WHITE)
    box_line(" 1. Разъём USB заблокирован: провод от ноутбука его не видит.", C_YELLOW)
    box_line(" 2. Свои приложения (Яндекс.Навигатор, YouTube) ставить нельзя — стоят 2 «охранника».", C_YELLOW)
    box_line(" 3. Любые временные изменения сбрасываются при перезапуске автомобиля.", C_YELLOW)
    box_line("Наша программа — это безопасный цифровой ключ, который всё настраивает.", C_GREEN)
    box_bottom()

    box_title("[МАСКА T1.0.0] КАК ОПРЕДЕЛИТЬ СВОЮ ВЕРСИЮ ПО ЗНАЧКАМ?")
    box_line("В настройках ГУ у всех автомобилей с завода пишется «T1.0.0».", C_WHITE)
    box_line("Но под этой надписью может скрываться 3 разных поколения системы:", C_WHITE)
    box_line("• Ветка 2.2.0 (ПЕРЕМЫЧКА ЗАКРЫТА!):", C_RED)
    box_line("  - Признак: в меню настроек / ассистентов вождения появился «Лимит скорости».", C_YELLOW)
    box_line("  - На ней завод Geely закрыл ADB при сбросе настроек: перемычка НЕ сработает!", C_RED)
    box_line("  - Если лимит скорости есть — не разбирайте салон! Нужен софтанлок (@eucsoft).", C_RED)
    box_line("• Ветка 2.1.4.5+ (ПЕРЕМЫЧКА РАБОТАЕТ):", C_GREEN)
    box_line("  - Признак: внизу на главном экране в строке климата появились мини-значки обогрева лобового стекла.", C_YELLOW)
    box_line("  - На ней защита Parrot отключается глобально через build.prop.", C_WHITE)
    box_line("• Ветка 2.1.3 / ранняя (ПЕРЕМЫЧКА РАБОТАЕТ):", C_GREEN)
    box_line("  - Признак: классический вид (нет ни лимита скорости, ни мини-значков обогрева внизу).", C_YELLOW)
    box_line("  - Защита Parrot вшита: программа ставит переключатель через доверенный ключ (Parrot Trust).", C_WHITE)
    box_line("(Точную версию знает только сканер GLDS у дилера, но эти значки спасут от разборки салона).", C_GRAY)
    box_bottom()

    box_title("[!] В ЧЁМ РАЗНИЦА: ПУНКТ 1 ИЛИ ПУНКТ 2?")
    box_line("• Пункт [1] — Снятие защиты установки (Универсально под любую версию):", C_YELLOW)
    box_line("  ВАЖНО: Пункт [1] НЕ открывает закрытый порт ADB! Он нужен, если провод УЖЕ видит ГУ", C_RED)
    box_line("  (открывали ранее, либо обновились у дилера, либо купили с открытым портом).", C_WHITE)
    box_line("  Перемычка и сброс НЕ нужны: скрипт сам аппаратно поймет версию (2.1.3 с Parrot Trust,", C_GREEN)
    box_line("  2.1.4.5 со снятием app_verify или 2.2.0 с изоляцией scratch) и всё сделает за вас.", C_GREEN)
    box_line("• Пункт [2] — Открыть ADB с нуля (порт закрыт с завода):", C_CYAN)
    box_line("  Если машина новая и ноутбук не видит ГУ по кабелю. Нужна перемычка и сброс ГУ,", C_WHITE)
    box_line("  но ТОЛЬКО если у вас прошивка до 2.2.0 (нет лимита скорости в меню).", C_GREEN)
    box_bottom()

    box_title("[ШАГ 1] ОТКРЫВАЕМ СЛУЖЕБНУЮ СВЯЗЬ (ADB)")
    box_line("• Зачем перемычка? Завод оставил для инженеров тайную лазейку. При замыкании", C_WHITE)
    box_line("  двух контактов планшет думает: «Я на сервисе, нужно приоткрыть сервисный порт».", C_WHITE)
    box_line("• Зачем сброс настроек? При сбросе к заводским настройкам (в меню авто)", C_WHITE)
    box_line("  планшет перезагружается и ровно на 20 секунд открывает служебное окно.", C_WHITE)
    box_line("• Что делает программа? Компьютер ловит эти 20 секунд и молниеносно отправляет", C_CYAN)
    box_line("  команду фиксации VHAL: «Включить постоянный ADB!». Планшет сохраняет флаг.", C_CYAN)
    box_line("  После этого перемычку снимают навсегда — порт больше никогда не закроется.", C_GREEN)
    box_bottom()

    box_title("[ШАГ 2] УСЫПЛЯЕМ «ОХРАННИКОВ», ЗАПРЕЩАЮЩИХ УСТАНОВКУ")
    box_line("1. Охранник «Parrot» (Попугай) на 2.1.4.5 проверял цифровую подпись завода Geely.", C_WHITE)
    box_line("   Если подписи нет — выкидывал APK. Мы переключаем app_verify=false.", C_CYAN)
    box_line("   На прошивках 2.2.0 и после GMC Parrot уже снят производителем, но требуются", C_GREEN)
    box_line("   открытие системных разделов и безопасная очистка старых слоев scratch.", C_GREEN)
    box_line("2. Охранник «AutoInstallVerifier» — системный робот, блокирующий установку APK.", C_WHITE)
    box_line("   Программа отключает этого робота для всех профилей пользователей ГУ.", C_GREEN)
    box_bottom()

    box_title("[ШАГ 3] ТУМБЛЕР (ADB TOGGLE), ТВИКИ GEELYTUNE И ПРИЛОЖЕНИЯ")
    box_line("• На экран ГУ ставится тумблер ADB Toggle: в один клик можно переключать разъём", C_WHITE)
    box_line("  между обычной флешкой с музыкой и кабелем отладки.", C_WHITE)
    box_line("• Открывается GeelyTune для установки помощника ГУ и удобных твиков интерфейса.", C_CYAN)
    box_line("  На 2.1.3 при предупреждении нажмите на сайте «Разрешить GeelyTune на этой прошивке».", C_YELLOW)
    box_line("• Приложения на 2.1.4.5+ и 2.2.0 ставятся свободно с https://ex5app.wingie.ru/ (автор @wingus).", C_GREEN)
    box_line("  На ветке 2.1.3 магазин не поддерживает подпись — ставьте любые APK через пункт [T] в нашей программе.", C_YELLOW)
    box_bottom()

    box_title("[ПАМЯТКА] ПРАВИЛА ПОЕЗДКИ К ДИЛЕРУ И ОБНОВЛЕНИЯ ДО 2.2.0")
    box_line("1. ПЕРЕД визитом к дилеру ОБЯЗАТЕЛЬНО включите тумблер ADB в положение ВКЛ!", C_RED)
    box_line("   Дилеры часто сбрасывают ГУ на заводские настройки перед прошивкой. Если ADB выключен,", C_WHITE)
    box_line("   а дилер зальёт 2.2.0 — перемычка больше не сработает и ADB закроется навсегда!", C_RED)
    box_line("2. ПЕРЕД обновлением до 2.2.0 удалите компоненты GeelyTune (в меню GeelyTune).", C_YELLOW)
    box_line("   Это предотвратит конфликт старых оверлеев с новой прошивкой.", C_WHITE)
    box_line("3. Владельцам кастомных прошивок GMC:", C_YELLOW)
    box_line("   Обновляйтесь у авторов GMC или просите дилера удалить её, иначе слетит ADB.", C_WHITE)
    box_line("4. ПОСЛЕ обновления у дилера до 2.2.0 / GMC — СРАЗУ запустите Пункт [1] нашей программы!", C_GREEN)
    box_line("   Пункт [1] — это официальный скрипт адаптации GeelyTune (https://t.me/geelyex5emidev/5/48009).", C_CYAN)
    box_line("   Он отодвинет старые слои в scratch, снимет блокировки и подготовит ГУ к установке GT.", C_GREEN)
    box_bottom()

    box_title("[БЕЗОПАСНОСТЬ] ЧТО С МАШИНОЙ И ПЛАНШЕТОМ?")
    box_line("• Мы НЕ трогаем прошивку двигателя, тормозов, рулевого управления или подушек.", C_WHITE)
    box_line("• Системные разделы защищены: изменения накладываются через виртуальный слой (overlay).", C_WHITE)
    box_line("• Заводские файлы не перезаписываются, а старые временные слои безопасно изолируются.", C_WHITE)
    box_line("• Европейские версии (e245_eu) определяются программно и защищены от лишних перезагрузок.", C_WHITE)
    box_bottom()

    box_title("[ОБ АВТОРЕ СБОРКИ И ИСТОРИИ ПРОЕКТА (@leonkil318)]")
    box_line("• Сразу уточню: автором этих скриптов я не являюсь. В нашей ветке ADB за всё", C_WHITE)
    box_line("  время её существования накопилось немало скриптов и наработок. Я лишь собрал", C_WHITE)
    box_line("  их воедино, добавил встроенный ADB и обернул в удобную консольную оболочку.", C_WHITE)
    box_line("• Все сообщения об ошибках переведены на человеческий русский язык.", C_CYAN)
    box_line("• Программа завершается корректно через пункт [0] Меню или сочетанием клавиш Ctrl+C.", C_WHITE)
    box_line("• Если есть конструктивные предложения или замечания — пишите @leonkil318.", C_GREEN)
    box_bottom()

    print()
    try:
        input(f"{C_CYAN}Нажмите Enter для перехода в главное меню приложения...{C_RESET}")
    except (KeyboardInterrupt, EOFError):
        pass


def scroll_to_top():
    """Scrolls the Windows console viewport to the top (0, 0) so the first line is visible."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        hOut = kernel32.CreateFileW("CONOUT$", 0x80000000 | 0x40000000, 3, None, 3, 0, None)
        if hOut != -1:
            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [
                    ('dwSize_X', ctypes.c_short), ('dwSize_Y', ctypes.c_short),
                    ('dwCursorPosition_X', ctypes.c_short), ('dwCursorPosition_Y', ctypes.c_short),
                    ('wAttributes', ctypes.c_ushort),
                    ('srWindow_Left', ctypes.c_short), ('srWindow_Top', ctypes.c_short),
                    ('srWindow_Right', ctypes.c_short), ('srWindow_Bottom', ctypes.c_short),
                    ('dwMaximumWindowSize_X', ctypes.c_short), ('dwMaximumWindowSize_Y', ctypes.c_short),
                ]
            class SMALL_RECT(ctypes.Structure):
                _fields_ = [('Left', ctypes.c_short), ('Top', ctypes.c_short),
                            ('Right', ctypes.c_short), ('Bottom', ctypes.c_short)]

            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if kernel32.GetConsoleScreenBufferInfo(hOut, ctypes.byref(csbi)):
                w = csbi.srWindow_Right - csbi.srWindow_Left
                h = csbi.srWindow_Bottom - csbi.srWindow_Top
                rect = SMALL_RECT(0, 0, w, h)
                kernel32.SetConsoleWindowInfo(hOut, True, ctypes.byref(rect))
            kernel32.CloseHandle(hOut)
    except Exception:
        pass


def render_author_disclaimer(W=None):
    """Renders author's note and disclaimer before program start with full original text and aligned borders."""
    if W is None:
        W = get_terminal_width()
    inner = W - 4

    def box_title(title):
        t = f"┌─ {title} "
        dash = max(2, W - visible_len(t) - 1)
        print(f"{C_CYAN}{t}{'─' * dash}┐{C_RESET}")

    def box_line(text, color=C_WHITE):
        clean = ANSI_REGEX.sub('', text)
        if not clean:
            p = " " * inner
            print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")
            return
        for line in textwrap.wrap(clean, width=inner, subsequent_indent="  "):
            p = pad_box_line(f"{color}{line}{C_RESET}", inner)
            print(f"{C_CYAN}│{C_RESET} {p} {C_CYAN}│{C_RESET}")

    def box_bottom():
        print(f"{C_CYAN}└{'─' * (W - 2)}┘{C_RESET}")

    box_title("ВАЖНОЕ ОБРАЩЕНИЕ ОТ АВТОРА СБОРКИ (@leonkil318)")
    box_line("Сразу уточню: автором этих скриптов я не являюсь. В нашей ветке ADB за всё", C_WHITE)
    box_line("время её существования, по мере появления разных версий машин, накопилось", C_WHITE)
    box_line("немало различных скриптов и наработок. Я лишь собрал их воедино, добавил", C_WHITE)
    box_line("необходимые зависимости и сделал из этого удобный инструмент для тех, кто", C_WHITE)
    box_line("не хочет или не умеет самостоятельно разбираться в командной строке.", C_WHITE)
    box_line("", C_WHITE)
    box_line("По сути, я просто обернул штатные ADB-операции в понятную оболочку, а сообщения", C_CYAN)
    box_line("об ошибках, где это было необходимо, перевёл на человеческий русский язык,", C_CYAN)
    box_line("чтобы было понятно, что происходит и что делать дальше.", C_CYAN)
    box_line("", C_WHITE)
    box_line("Скрипт собирался со всеми необходимыми зависимостями — ничего дополнительно", C_WHITE)
    box_line("скачивать из интернета или устанавливать отдельно, в том числе ADB, не требуется.", C_WHITE)
    box_line("Никакого лишнего функционала вроде Fastboot там нет.", C_WHITE)
    box_line("", C_WHITE)
    box_line("Обкладывать его проверками на все возможные сценарии, включая закрытие CMD", C_YELLOW)
    box_line("крестиком, я не вижу смысла. Это консольное приложение, и способ его корректного", C_YELLOW)
    box_line("завершения был отдельно указан: только через пункт [0] Меню или Ctrl+C.", C_YELLOW)
    box_line("", C_WHITE)
    box_line("Скрипт свою задачу выполняет. Если не соблюдать указанный порядок работы,", C_WHITE)
    box_line("некорректное завершение процесса вполне ожидаемо. Это не означает, что сам", C_WHITE)
    box_line("инструмент нуждается в дополнительных проверках на все случаи жизни.", C_WHITE)
    box_line("", C_WHITE)
    box_line("Если есть конкретные предложения по улучшению или замечания по работе —", C_GREEN)
    box_line("пишите. Если они действительно имеют смысл, я доработаю.", C_GREEN)
    box_line("", C_WHITE)
    box_line("[!] ПРЕДУПРЕЖДЕНИЕ И ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ (DISCLAIMER):", C_RED)
    box_line("Всё, что вы делаете со своим автомобилем, мультимедиа-системой и электронными", C_YELLOW)
    box_line("блоками, вы делаете ИСКЛЮЧИТЕЛЬНО НА СВОЙ СТРАХ И РИСК!", C_RED)
    box_line("Ни автор этой сборки (@leonkil318), ни авторы оригинальных скриптов не несут", C_YELLOW)
    box_line("никакой ответственности за возможные последствия: потерю заводской гарантии,", C_YELLOW)
    box_line("сбои в работе ГУ, зависания, окирпичивание («кирпич»), закрытие портов или", C_YELLOW)
    box_line("любой иной ущерб вашему имуществу. Если вы не уверены в своих действиях или", C_YELLOW)
    box_line("не понимаете, что делаете — немедленно закройте программу и обратитесь к специалистам.", C_YELLOW)
    box_bottom()
    scroll_to_top()


def render_exit_screen(seconds=5):
    """Displays a large, centered farewell message on exit and holds for specified seconds."""
    clear_screen()
    W = get_terminal_width()
    inner = max(40, min(W - 4, 90))

    banner_lines = [
        "",
        "★ ★ ★   ПРИЯТНЫХ ПОЕЗДОК И УДАЧИ НА ДОРОГАХ!   ★ ★ ★",
        "",
        "Берегите себя и свой Geely! Пусть каждая поездка приносит радость.",
        "Спасибо за доверие и взаимное уважение в сообществе!",
        "",
        f"До новых встреч на трассе! Окно закроется через {seconds} сек...",
        ""
    ]

    # Vertical centering padding
    pad_top = max(1, (24 - len(banner_lines) - 4) // 2)
    sys.stdout.write("\n" * pad_top)

    # Horizontal centering of box
    margin = " " * max(0, (W - inner - 2) // 2)

    print(f"{margin}{C_GREEN}╔" + ("═" * inner) + f"╗{C_RESET}")
    for line in banner_lines:
        v = visible_len(line)
        left = max(0, (inner - v) // 2)
        right = max(0, inner - v - left)
        print(f"{margin}{C_GREEN}║{C_RESET}{' ' * left}{C_WHITE}{C_BOLD}{line}{C_RESET}{' ' * right}{C_GREEN}║{C_RESET}")
    print(f"{margin}{C_GREEN}╚" + ("═" * inner) + f"╝{C_RESET}")

    sys.stdout.flush()
    time.sleep(seconds)

