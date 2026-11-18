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
    stop_adb_server,
    check_devices,
    test_adb_connection,
    run_adb,
    worker_catch_factory_reset,
    worker_reboot_and_verify,
    worker_unlock_and_install,
    worker_install_via_parrot_trust
)

from tui import (
    init_terminal,
    clear_screen,
    print_banner,
    render_diagnostic_card,
    render_menu,
    render_recent_logs,
    run_interactive_task,
    render_help_screen,
    C_RESET,
    C_BOLD,
    C_CYAN,
    C_GREEN,
    C_YELLOW,
    C_RED,
    C_WHITE,
    C_GRAY
)

from sound import toggle_sound, play_sound


def safe_input(prompt, default=""):
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        return default


def run_full_wizard():
    """Runs the wizard for initial ADB unlock with factory reset."""
    clear_screen()
    print_banner()
    print(f"\n{C_CYAN}{C_BOLD}[*] СЦЕНАРИЙ: ПЕРВОНАЧАЛЬНАЯ РАЗБЛОКИРОВКА ADB{C_RESET}\n")
    print(f"{C_WHITE}ГОТОВНОСТЬ К ПЕРЕХВАТУ:{C_RESET}")
    print(" 1. Кабель USB-A ↔ USB-A соединяет ноутбук и штатный порт автомобиля.")
    print(" 2. Отключите от ноутбука лишние телефоны и планшеты во избежание путаницы.")
    print(" 3. Перемычка установлена в разъём, экран ГУ активен.")
    print(" 4. Для Windows 11: используйте прямой USB-порт без переходников и USB-хабов.")
    print(" 5. После подтверждения запустится адаптивный скоростной перехват сервисного окна.")
    print(f" 6. На экране авто перейдите:")
    print(f"    {C_YELLOW}Основное приложение ➔ Мой автомобиль ➔ Сброс к заводским настройкам{C_RESET}")
    print("    и согласитесь с предупреждениями (будут сброшены личные профили мультимедиа).\n")
    
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
    print(f"\n{C_GREEN}{C_BOLD}[OK] VHAL ЗАФИКСИРОВАН (Set property получен)!{C_RESET}\n")
    print(f"{C_WHITE}ДЕЙСТВИЯ С ПЕРЕМЫЧКОЙ:{C_RESET}")
    print(f" 1. {C_YELLOW}Аккуратно снимите перемычку.{C_RESET}")
    print(" 2. Кабель USB остаётся подключенным к ГУ.\n")
    
    ans = safe_input(f"{C_CYAN}Перемычка снята? [Enter - Перезагрузить ГУ и проверить ADB, 0 - Отмена] > {C_RESET}", default="0").strip()
    if ans == "0":
        return
    run_interactive_task(STATE, worker_reboot_and_verify, "Шаг 3: Перезагрузка ГУ и проверка постоянного ADB")
    if STATE.status != "success":
        return

    # Step 4: Unlock Parrot & Install Toggle
    run_interactive_task(STATE, worker_unlock_and_install, "Шаг 4: Снятие Parrot, отключение верификатора и установка тумблера")
    if STATE.status == "success":
        post_unlock_prompt()


def run_quick_unlock():
    """Runs quick unlock for cars with existing ADB after dealer 2.1.4.5+, 2.2.0 or GMC update."""
    clear_screen()
    print_banner()
    print(f"\n{C_CYAN}{C_BOLD}[*] ПУНКТ 1: СНЯТИЕ ЗАЩИТЫ УСТАНОВКИ (2.1.4.5 / 2.2.0 / ПОСЛЕ GMC){C_RESET}\n")
    print(f"{C_RED}{C_BOLD}⚠️  ВНИМАНИЕ: ПУНКТ [1] НЕ ОТКРЫВАЕТ ЗАКРЫТЫЙ С ЗАВОДА ПОРТ ADB!{C_RESET}")
    print(f"{C_YELLOW}Этот пункт предназначен ТОЛЬКО для автомобилей, где ADB УЖЕ БЫЛ ОТКРЫТ ранее{C_RESET}")
    print("(например, вы открывали его ранее, а затем обновились у дилера до 2.1.4.5 / 2.2.0")
    print("или получили обновление после GMC, из-за чего заблокировалась установка сторонних APK).\n")
    print(f"{C_GREEN}• Перемычка и сброс настроек НЕ ТРЕБУЮТСЯ!{C_RESET}")
    print("• Скрипт автоматически распознает прошивку авто:")
    print("  - На 2.1.4.5: отключает защиту Parrot certificates в build.prop;")
    print("  - На 2.2.0 / GMC: открывает системные разделы и изолирует старые оверлеи в scratch;")
    print("  - На всех версиях: отключает AutoInstallVerifier и ставит переключатель Geely-ADB-Toggle.\n")
    print(f"{C_GRAY}Если на автомобиле ADB ещё закрыт с завода — вернитесь назад и выберите [2] (Открыть ADB с нуля).{C_RESET}\n")

    # Guard: check if vehicle responds over ADB
    if STATE.device_state != "connected":
        code, stdout, _ = run_adb(["get-state"], timeout=2)
        if code != 0 or stdout.strip() != "device":
            print(f"{C_YELLOW}[!] Внимание: автомобиль сейчас не отвечает по ADB.{C_RESET}")
            print(f"Если ADB закрыт с завода, Пункт [1] не сработает — выберите в меню {C_BOLD}[2] Открыть ADB с нуля{C_RESET}.")
            print("Если ADB уже был открыт, проверьте плотность подключения кабеля USB-A.\n")

    ans = safe_input(f"{C_CYAN}Запустить процедуру снятия защит установки? [Enter - Да, 0 - Назад] > {C_RESET}", default="0").strip()
    if ans == "0":
        return

    # Run quick unlock
    run_interactive_task(STATE, worker_unlock_and_install, "Экспресс-снятие защиты установки (2.1.4.5 / 2.2.0 / GMC)")
    if STATE.status == "success":
        post_unlock_prompt()


def post_unlock_prompt():
    """Prompt after successful unlock to open ex5app store or GeelyTune."""
    clear_screen()
    print_banner()
    print(f"\n{C_GREEN}{C_BOLD}[OK] ПОЗДРАВЛЯЕМ! РАЗБЛОКИРОВКА ПОЛНОСТЬЮ ЗАВЕРШЕНА!{C_RESET}\n")
    print(" • Постоянный ADB: активен")
    print(" • Проверка Parrot certificates / верификаторы: отключены (установка APK разрешена)")
    print(" • Проверяющий AutoInstallVerifier: отключен")
    print(" • Приложение Geely-ADB-Toggle: готово к работе на экране авто\n")
    print(f"{C_CYAN}КУДА ПЕРЕЙТИ ДАЛЬШЕ?{C_RESET}")
    print(f" {C_GREEN}[1]{C_RESET} Открыть веб-магазин {C_BOLD}EX5 Apps{C_RESET} (https://ex5app.wingie.ru/ — софт от @wingus через браузер)")
    print(f" {C_WHITE}[2]{C_RESET} Открыть веб-сервис {C_BOLD}GeelyTune{C_RESET} (https://geelytune.github.io — твики ГУ)")
    print(f" {C_GRAY}[0] Вернуться в главное меню{C_RESET}\n")
    
    ans = safe_input(f"{C_CYAN}Выберите действие [1, 2, 0] > {C_RESET}", default="1").strip()
    if ans == "1":
        print(f"\n{C_CYAN}Освобождаем USB-разъём (завершаем фоновые процессы adb.exe)...{C_RESET}")
        stop_adb_server()
        print(f"{C_GREEN}[OK] Служба ADB остановлена. Порт полностью свободен для браузера (WebUSB)!{C_RESET}")
        webbrowser.open("https://ex5app.wingie.ru/")
        print(f"{C_WHITE}В открывшейся вкладке нажмите «Подключить» и устанавливайте софт прямо из браузера.{C_RESET}")
        time.sleep(2)
    elif ans == "2":
        print(f"\n{C_CYAN}Освобождаем USB-разъём (завершаем фоновые процессы adb.exe)...{C_RESET}")
        stop_adb_server()
        print(f"{C_GREEN}[OK] Служба ADB остановлена. Порт полностью свободен для браузера (WebUSB)!{C_RESET}")
        webbrowser.open("https://geelytune.github.io")
        print(f"{C_WHITE}В открывшейся вкладке нажмите «Подключить» и выберите ваш автомобиль.{C_RESET}")
        time.sleep(2)


def run_parrot_trust_wizard():
    """Wizard for installing an APK on early firmware (pre-2.1.4.5) via Parrot Trust."""
    clear_screen()
    print_banner()
    print(f"\n{C_CYAN}{C_BOLD}[*] УСТАНОВКА APK ЧЕРЕЗ PARROT TRUST (ДЛЯ РАННИХ ПРОШИВОК < 2.1.4.5){C_RESET}\n")
    print(f"{C_YELLOW}ВНИМАНИЕ:{C_RESET}")
    print(" • Этот инструмент нужен ТОЛЬКО для ранних прошивок (до 2.1.4.5),")
    print("   где проверка Parrot вшита намертво и не имеет глобального выключателя.")
    print(f" • {C_GREEN}Если у вас прошивка 2.1.4.5+ или 2.2.0 — вам это НЕ НУЖНО!{C_RESET}")
    print("   (используйте пункт [1] в меню, и любые APK будут ставиться без ограничений).\n")

    # Look for any apk files in workspace or core
    found_apks = []
    root_dir = os.path.dirname(CURRENT_DIR)
    for search_dir in [root_dir, CURRENT_DIR]:
        if os.path.isdir(search_dir):
            for f in os.listdir(search_dir):
                if f.lower().endswith(".apk") and not f.startswith("."):
                    full_p = os.path.join(search_dir, f)
                    if full_p not in found_apks:
                        found_apks.append(full_p)

    if found_apks:
        print(f"{C_WHITE}Найденные APK файлы в проекте:{C_RESET}")
        for idx, apk in enumerate(found_apks, 1):
            print(f" [{idx}] {os.path.basename(apk)}")
        print()

    apk_input = safe_input(f"{C_CYAN}Введите путь к APK-файлу (или номер из списка выше, 0 - Отмена) > {C_RESET}").strip()
    if apk_input in ["0", "", "q"]:
        return

    selected_apk = None
    if apk_input.isdigit() and 1 <= int(apk_input) <= len(found_apks):
        selected_apk = found_apks[int(apk_input) - 1]
    elif os.path.isfile(apk_input.strip('"').strip("'")):
        selected_apk = os.path.abspath(apk_input.strip('"').strip("'"))
    else:
        print(f"\n{C_RED}[!] Файл не найден: {apk_input}{C_RESET}")
        time.sleep(2)
        return

    print(f"\n{C_WHITE}Выбран файл: {C_CYAN}{selected_apk}{C_RESET}")
    ans = safe_input(f"{C_CYAN}Начать установку через Parrot Trust? [Enter - Да, 0 - Отмена] > {C_RESET}").strip()
    if ans == "0":
        return

    run_interactive_task(
        STATE,
        lambda: worker_install_via_parrot_trust(selected_apk),
        f"Установка {os.path.basename(selected_apk)} через Parrot Trust"
    )


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

        choice = safe_input(f"\n{C_CYAN}{C_BOLD}Выберите пункт меню [0-8, T - Parrot Trust, S - Звук, ? - Справка] > {C_RESET}", default="0").strip()

        if choice == "1":
            play_sound("step")
            run_quick_unlock()
        elif choice == "2":
            play_sound("step")
            run_full_wizard()
        elif choice == "3":
            play_sound("step")
            run_interactive_task(STATE, test_adb_connection, "Диагностика связи и проверка статуса ГУ")
        elif choice == "4":
            play_sound("step")
            print(f"\n{C_CYAN}Освобождаем USB-разъём (завершаем фоновые процессы adb.exe)...{C_RESET}")
            stop_adb_server()
            print(f"{C_GREEN}[OK] Служба ADB остановлена. Порт свободен для браузера (WebUSB)!{C_RESET}")
            webbrowser.open("https://geelytune.github.io")
            STATE.log("Служба ADB остановлена. Открыт GeelyTune (твики ГУ): https://geelytune.github.io", "success")
            time.sleep(1.5)
        elif choice == "5":
            play_sound("step")
            print(f"\n{C_CYAN}Освобождаем USB-разъём (завершаем фоновые процессы adb.exe)...{C_RESET}")
            stop_adb_server()
            print(f"{C_GREEN}[OK] Служба ADB остановлена. Порт свободен для браузера (WebUSB)!{C_RESET}")
            webbrowser.open("https://ex5app.wingie.ru/")
            STATE.log("Служба ADB остановлена. Открыт веб-установщик EX5 Apps: https://ex5app.wingie.ru/", "success")
            print(f"{C_WHITE}В браузере откроется каталог приложений от @wingus.{C_RESET}")
            print(f"{C_WHITE}Нажмите «Подключить» в браузере и устанавливайте приложения прямо через WebUSB!{C_RESET}")
            time.sleep(2)
        elif choice == "6":
            play_sound("step")
            run_interactive_task(STATE, kill_adb_processes, "Перезапуск службы ADB")
            check_devices()
        elif choice.lower() in ["t", "е", "trust"]:
            play_sound("step")
            run_parrot_trust_wizard()
        elif choice.lower() in ["7", "s", "ы"]:
            enabled = toggle_sound()
            status_str = "ВКЛЮЧЕНЫ" if enabled else "ВЫКЛЮЧЕНЫ"
            STATE.log(f"Звуковые эффекты: {status_str}", "info")
        elif choice.lower() in ["8", "?", "help", "h", "справка", "инфо"]:
            play_sound("step")
            render_help_screen()
        elif choice in ["0", "q", "exit", "quit"]:
            play_sound("step")
            stop_adb_server()
            print(f"\n{C_GREEN}Завершение работы. Удачи на дорогах!{C_RESET}")
            time.sleep(0.5)
            break
        else:
            time.sleep(0.2)



if __name__ == "__main__":
    main()
