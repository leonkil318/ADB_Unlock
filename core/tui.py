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
    """Initializes terminal encoding and enables ANSI processing on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
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


def print_banner():
    """Renders the cyan hacker-style header banner adaptively to window width."""
    W = get_terminal_width()
    inner = W - 2

    top = f"{C_CYAN}╔" + ("═" * inner) + f"╗{C_RESET}"
    bot = f"{C_CYAN}╚" + ("═" * inner) + f"╝{C_RESET}"

    t1 = "GEELY ADB UNLOCK MASTER v2.1.4.5"
    t2 = "Flyme Auto / Ecarx Service Terminal • EX5 EM-i / X80"

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

    t = state.last_test or {}
    connected = t.get("connected", state.device_state == "connected")
    serial = t.get("serial") or state.device_serial or "Не обнаружено"
    model = t.get("model") or ("Штатное ГУ Geely" if connected else "-")
    firmware = t.get("firmware") or ("2.1.4.5+" if connected else "-")

    if connected:
        adb_badge = f"{C_GREEN}[ АКТИВЕН ]{C_RESET}"
    elif t.get("state") == "unauthorized":
        adb_badge = f"{C_YELLOW}[ ТРЕБУЕТ ДОПУСК ]{C_RESET}"
    else:
        adb_badge = f"{C_RED}[ НЕ ПОДКЛЮЧЕН ]{C_RESET}"

    if connected:
        if t.get("parrot_locked"):
            parrot_badge = f"{C_YELLOW}[ БЛОКИРУЕТ ]{C_RESET}"
        else:
            parrot_badge = f"{C_GREEN}[ ВЫКЛЮЧЕНА ]{C_RESET}"

        if t.get("verifier_active"):
            verifier_badge = f"{C_YELLOW}[ АКТИВЕН ]{C_RESET}"
        else:
            verifier_badge = f"{C_GREEN}[ ОТКЛЮЧЕН ]{C_RESET}"
    else:
        parrot_badge = f"{C_GRAY}[ - ]{C_RESET}"
        verifier_badge = f"{C_GRAY}[ - ]{C_RESET}"

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
        l2_c2 = f"Прошивка:    {C_CYAN}{firmware}{C_RESET}"
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
        print_single(f"Прошивка:      {C_CYAN}{firmware}{C_RESET}")
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
        print_menu_item(f"{C_GREEN}{C_BOLD}[1] Экспресс-снятие защиты (ОД 2.1.4.5+, перемычка НЕ требуется){C_RESET}")
    else:
        print_menu_item(f"{C_WHITE}[1]{C_RESET} Экспресс-снятие защиты (После обновления ОД 2.1.4.5+, если ADB уже был)")

    print_menu_item(f"{C_WHITE}[2]{C_RESET} Первоначальная разблокировка (Фиксация ADB через Factory Reset)")
    print_menu_item(f"{C_WHITE}[3]{C_RESET} Проверить статус ГУ (Диагностика связи и состояния блокировок)")
    print_menu_item(f"{C_WHITE}[4]{C_RESET} Открыть веб-установщик GeelyTune (в браузере)")
    print_menu_item(f"{C_WHITE}[5]{C_RESET} Перезапустить службу ADB (Очистить зависшие процессы)")
    sound_badge = f"{C_GREEN}[ ВКЛ ]{C_RESET}" if is_sound_enabled() else f"{C_GRAY}[ ВЫКЛ ]{C_RESET}"
    print_menu_item(f"{C_WHITE}[6]{C_RESET} Звуковые эффекты и мелодия Zelda: {sound_badge}")
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
