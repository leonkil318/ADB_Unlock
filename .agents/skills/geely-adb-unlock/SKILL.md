---
name: geely-adb-unlock
description: >-
  Expert guide and runbook for maintaining, troubleshooting, and extending the Geely ADB Unlock Master
  application. Use this skill whenever working on Geely multimedia head unit (HU) unlock workflows,
  modifying core/engine.py, editing the native TUI in core/tui.py, building launchers, or debugging ADB and VHAL connections.
---

# Geely ADB Unlock Master — База знаний и руководство разработчика

Этот скил содержит полное описание устройства, процедур сборки, отладки и модификации проекта **Geely ADB Unlock Master**.

---

## 1. Архитектура приложения

Приложение построено по схеме **Zero-Dependency Native TUI/CLI Application**:

```text
               ┌────────────────────────────────────────────────────────┐
               │        Окно консоли (cmd / PowerShell / Terminal)      │
               │        Строгий ретро TUI-интерфейс (core/tui.py)       │
               └──────────────────────────┬─────────────────────────────┘
                                          │  Прямые вызовы функций Python
                                          ▼
               ┌────────────────────────────────────────────────────────┐
               │         Движок бизнес-логики (core/engine.py)          │
               │    или автономный бинарник core/geely_unlock.exe       │
               └──────────────────────────┬─────────────────────────────┘
                                          │
                                          │  Команды ADB (subprocesses)
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │            Встроенный Google ADB (core/bin/adb.exe / -darwin / -linux)      │
   └──────────────────────────────────────┬─────────────────────────────────────┘
                                          │  USB-кабель
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │                  Автомобиль Geely (Головное устройство)                    │
   │   - VHAL: lshal ... --set 557872680 i 0 a 0 (USB_SWITCH=0)                 │
   │   - Скрипт: unlock-hu.sh (отключение Parrot & AutoInstallVerifier)         │
   │   - Пакет: Geely-ADB-Toggle-1.1.0.apk (--user 10)                          │
   └────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Ключевые компоненты

### 1. `core/engine.py`
* Чистая бизнес-логика без привязки к интерфейсу.
* Фоновые потоки `threading.Thread` для долгих операций (захват VHAL, опрос перезагрузки ГУ, выполнение `unlock-hu.sh`).
* Очистка зависших процессов ADB.
* Функция `get_resource_path()` для корректной работы с ресурсами из `sys._MEIPASS` при сборке в один `.exe`.

### 2. `core/tui.py`
* Zero-Dependency отрисовка интерфейса через чистые ANSI-коды.
* Автоматическая активация ANSI VT100 на Windows (`SetConsoleMode`).
* Статус-панель связи с ГУ, блокировок Parrot и AutoInstallVerifier.
* Интерактивное меню с цифрами [0-5], живой терминальный логгер с анимированным спиннером.

### 3. `core/main.py`
* Главная точка входа консольного приложения.

### 4. Бинарники `core/bin/`
* `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` — для Windows.
* `adb-darwin` — для macOS (Universal x86_64 / arm64).
* `adb-linux` — для Linux (x86_64).

---

## 3. Процедуры обслуживания и сборки

### Как пересобрать `core/geely_unlock.exe` (для Windows)
Автономный исполняемый файл пересобирается с упаковкой ресурсов внутрь:

```cmd
cd /d d:\ADB_Unlock\core
python -m PyInstaller --clean --onefile --name "geely_unlock" --distpath "d:\ADB_Unlock\core" --workpath "d:\ADB_Unlock\core\build" --specpath "d:\ADB_Unlock\core" --add-data "d:\ADB_Unlock\core\bin\adb.exe;bin" --add-data "d:\ADB_Unlock\core\bin\AdbWinApi.dll;bin" --add-data "d:\ADB_Unlock\core\bin\AdbWinUsbApi.dll;bin" --add-data "d:\ADB_Unlock\core\unlock-hu.sh;." --add-data "d:\ADB_Unlock\core\Geely-ADB-Toggle-1.1.0.apk;." "d:\ADB_Unlock\core\main.py"
```

После сборки удалить временные файлы:
```powershell
Remove-Item -Recurse -Force 'd:\ADB_Unlock\core\build', 'd:\ADB_Unlock\core\geely_unlock.spec'
```

### Как тестировать macOS и Linux на Windows
1. **Синтаксическая проверка скриптов запуска:**
   ```bash
   "C:\Program Files\Git\bin\bash.exe" -n d:/ADB_Unlock/СТАРТ_Linux.sh
   "C:\Program Files\Git\bin\bash.exe" -n d:/ADB_Unlock/СТАРТ_Mac.command
   ```
2. **Проверка эмуляции macOS в Python:**
   ```cmd
   python -c "import platform; platform.system = lambda: 'Darwin'; exec(open('d:/ADB_Unlock/core/main.py', encoding='utf-8').read())"
   ```

---

## 4. Часто встречающиеся проблемы и решения

### Проблема: Батник выдает странные ошибки команд на Windows
* **Причина:** Переводы строк `LF` вместо `CRLF` или кириллические символы в коде батника.
* **Решение:** Файл [СТАРТ_Windows.bat](file:///d:/ADB_Unlock/%D0%A1%D0%A2%D0%90%D0%A0%D0%A2_Windows.bat) должен содержать строго переносы `\r\n` (CRLF) и чистый ASCII-текст команд.

### Проблема: Ошибка «Must be root» или пропуск 20-секундного окна
* **Причина:** ГУ загрузилось слишком быстро или сброс был начат до запуска скрипта.
* **Решение:** Повторить сброс до заводских настроек на экране ГУ. Движок находится в бесконечном цикле опроса и автоматически перехватит следующую попытку.

### Проблема: Зависший процесс ADB в системе
* **Решение:** Выберите пункт 6 в главном меню приложения («Перезапуск службы ADB») или выполните в терминале `taskkill /F /IM adb.exe` (Windows) / `killall -9 adb` (macOS/Linux).

