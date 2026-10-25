"""
Geely ADB Unlock Master - Native CLI / TUI Application Entry Point
Standalone executable launcher without browser or local web server requirements.
"""

import sys
import os
import time
import webbrowser

# Add current directory to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from engine import (
    STATE,
    locate_or_download_adb,
    kill_adb_processes,
    check_devices,
    test_adb_connection,
    worker_catch_factory_reset,
    worker_reboot_and_verify,
    worker_unlock_and_install
)

from tui import (
    init_terminal,
    clear_screen,
    print_banner,
    render_diagnostic_card,
    render_menu,
    render_recent_logs,
    run_interactive_task,
    C_RESET,
    C_BOLD,
    C_CYAN,
    C_GREEN,
    C_YELLOW,
    C_RED,
    C_WHITE,
    C_GRAY
)


def safe_input(prompt, default=""):
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        return default


def run_full_wizard():
    """Runs the wizard for initial ADB unlock with factory reset."""
    clear_screen()
    print_banner()
    print(f"\n{C_CYAN}{C_BOLD}🔌 СЦЕНАРИЙ: ПЕРВОНАЧАЛЬНАЯ РАЗБЛОКИРОВКА ADB{C_RESET}\n")
    print(f"{C_WHITE}ГОТОВНОСТЬ К ПЕРЕХВАТУ:{C_RESET}")
    print(" 1. Кабель USB-A ↔ USB-A соединяет ноутбук и штатный порт автомобиля.")
    print(" 2. Перемычка установлена, зажигание включено (экран ГУ активен).")
    print(" 3. После подтверждения запустится цикл ожидания подключения.")
    print(" 4. Нажмите «Сброс до заводских настроек» (Factory Reset) в меню ГУ.\n")
    
    choice = safe_input(f"{C_CYAN}Готовы начать перехват сервисного окна? [Enter - Да, 0 - Отмена] > {C_RESET}", default="0").strip()
    if choice == "0":
        return

    # Step 2: Catch factory reset
    run_interactive_task(STATE, worker_catch_factory_reset, "Шаг 2: Ожидание сброса настроек ГУ и фиксация VHAL")
    if STATE.status != "success":
        return

    # Step 3: Remove jumper & reboot
    clear_screen()
    print_banner()
    print(f"\n{C_GREEN}{C_BOLD}✅ VHAL ЗАФИКСИРОВАН (Set property получен)!{C_RESET}\n")
    print(f"{C_WHITE}ДЕЙСТВИЯ С ПЕРЕМЫЧКОЙ:{C_RESET}")
    print(" 1. Выключите зажигание автомобиля.")
    print(f" 2. {C_YELLOW}Снимите перемычку.{C_RESET}")
    print(" 3. Снова включите зажигание авто (кабель USB остаётся подключенным).\n")
    
    safe_input(f"{C_CYAN}Перемычка снята? Нажмите Enter для перезагрузки ГУ и проверки ADB...{C_RESET}")
    run_interactive_task(STATE, worker_reboot_and_verify, "Шаг 3: Перезагрузка ГУ и проверка постоянного ADB")
    if STATE.status != "success":
        return

    # Step 4: Unlock Parrot & Install Toggle
    run_interactive_task(STATE, worker_unlock_and_install, "Шаг 4: Снятие Parrot, отключение верификатора и установка тумблера")
    if STATE.status == "success":
        post_unlock_prompt()


def run_quick_unlock():
    """Runs quick unlock for cars with existing ADB after dealer 2.1.4.5+ update."""
    clear_screen()
    print_banner()
    print(f"\n{C_CYAN}{C_BOLD}⚡ СЦЕНАРИЙ: ЭКСПРЕСС-СНЯТИЕ ЗАЩИТЫ (ОД 2.1.4.5+){C_RESET}\n")
    print(f"{C_GREEN}Перемычка НЕ требуется!{C_RESET}")
    print("Используется, если постоянный ADB в ГУ уже был активирован ранее.")
    print("Скрипт отключит блокировку Parrot в build.prop, выключит AutoInstallVerifier")
    print("и установит переключатель Geely-ADB-Toggle на экран мультимедиа.\n")

    ans = safe_input(f"{C_CYAN}Запустить процедуру снятия блокировок? [Enter - Да, 0 - Назад] > {C_RESET}", default="0").strip()
    if ans == "0":
        return

    # Run quick unlock
    run_interactive_task(STATE, worker_unlock_and_install, "Экспресс-снятие защиты Parrot и AutoInstallVerifier")
    if STATE.status == "success":
        post_unlock_prompt()


def post_unlock_prompt():
    """Prompt after successful unlock to open GeelyTune."""
    clear_screen()
    print_banner()
    print(f"\n{C_GREEN}{C_BOLD}🎉 ПОЗДРАВЛЯЕМ! РАЗБЛОКИРОВКА ПОЛНОСТЬЮ ЗАВЕРШЕНА!{C_RESET}\n")
    print(" • Постоянный ADB: активен")
    print(" • Проверка Parrot certificates: отключена (установка сторонних APK разрешена)")
    print(" • Проверяющий AutoInstallVerifier: отключен")
    print(" • Приложение Geely-ADB-Toggle: установлено на экран автомобиля\n")
    
    ans = safe_input(f"{C_CYAN}Открыть официальный веб-установщик GeelyTune в браузере? [Y/n] > {C_RESET}", default="n").strip().lower()
    if ans != "n":
        webbrowser.open("https://geelytune.github.io")
        print(f"{C_GREEN}Ссылка открыта в браузере: https://geelytune.github.io{C_RESET}")
        time.sleep(2)


def main():
    init_terminal()
    clear_screen()
    print_banner()
    print(f"\n{C_CYAN}Инициализация модулей и проверка ADB...{C_RESET}")
    
    locate_or_download_adb()
    check_devices()

    # Automatic quick test on startup if device is visible
    if STATE.device_state == "connected":
        test_adb_connection()

    while True:
        clear_screen()
        print_banner()
        render_diagnostic_card(STATE)
        render_menu(STATE)
        render_recent_logs(STATE, count=4)

        choice = safe_input(f"\n{C_CYAN}{C_BOLD}Выберите пункт меню [0-5] > {C_RESET}", default="0").strip()

        if choice == "1":
            run_quick_unlock()
        elif choice == "2":
            run_full_wizard()
        elif choice == "3":
            run_interactive_task(STATE, test_adb_connection, "Диагностика связи и проверка статуса ГУ")
        elif choice == "4":
            webbrowser.open("https://geelytune.github.io")
            STATE.log("Открыт сайт GeelyTune: https://geelytune.github.io", "success")
        elif choice == "5":
            run_interactive_task(STATE, kill_adb_processes, "Перезапуск службы ADB")
            test_adb_connection()
        elif choice in ["0", "q", "exit", "quit"]:
            print(f"\n{C_GREEN}Завершение работы. Удачи на дорогах!{C_RESET}")
            time.sleep(0.5)
            break
        else:
            time.sleep(0.2)



if __name__ == "__main__":
    main()
