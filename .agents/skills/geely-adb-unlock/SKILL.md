---
name: geely-adb-unlock
description: >-
  Expert guide and runbook for maintaining, troubleshooting, and extending the Geely ADB Unlock Master
  application. Use this skill whenever working on Geely multimedia head unit (HU) unlock workflows,
  modifying core/server.py, editing the web UI in core/web/index.html, building launchers, or debugging ADB and VHAL connections.
---

# Geely ADB Unlock Master — База знаний и руководство разработчика

Этот скил содержит полное описание устройства, процедур сборки, отладки и модификации проекта **Geely ADB Unlock Master**.

---

## 1. Архитектура приложения

Приложение построено по гибридной архитектуре: **Локальный оркестратор (Python / exe) + Адаптивный Web UI**.

```text
               ┌────────────────────────────────────────────────────────┐
               │                  Браузер пользователя                 │
               │   (http://127.0.0.1:8765 -> core/web/index.html)       │
               └──────────────────────────┬─────────────────────────────┘
                                          │  REST API (GET /api/status,
                                          │            POST /api/action)
                                          ▼
               ┌────────────────────────────────────────────────────────┐
               │          Локальный сервер (core/server.py)             │
               │    или скомпилированный бинарник core/geely_unlock.exe │
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

### 1. `core/server.py`
* Встроенный HTTP-сервер на базе стандартной библиотеки `http.server.HTTPServer`.
* Фоновые потоки `threading.Thread` для долгих операций (захват VHAL, опрос перезагрузки ГУ, выполнение `unlock-hu.sh`).
* Автоматическая кроссплатформенная очистка старых демонов ADB (`taskkill` / `killall`).
* Определение путей `BASE_DIR`:
  ```python
  if getattr(sys, 'frozen', False):
      BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
  else:
      BASE_DIR = os.path.dirname(os.path.abspath(__file__))
  ```

### 2. `core/web/index.html`
* Автономный одностраничный веб-интерфейс (HTML/CSS/JS без внешних npm-библиотек).
* 4-этапный мастер (Stepper):
  1. Подготовка и перемычка.
  2. Сброс настроек (Factory Reset) и автоматический захват 20-секундного окна.
  3. Извлечение перемычки и перезагрузка ГУ.
  4. Снятие ограничений установки и финал (переход к GeelyTune).
* Опрос состояния через `pollStatus()` раз в 1 секунду.
* Интерактивный терминал логов с автопрокруткой.
* Кнопка безопасного выгружения движка из памяти (`POST /api/action` с `action: shutdown`).

### 3. Бинарники `core/bin/`
* `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` — для Windows.
* `adb-darwin` — для macOS (Universal x86_64 / arm64).
* `adb-linux` — для Linux (x86_64).

---

## 3. Процедуры обслуживания и сборки

### Как пересобрать `core/geely_unlock.exe` (для Windows)
При изменении `core/server.py` автономный исполняемый файл пересобирается через PyInstaller:

```cmd
cd /d d:\ADB_Unlock\core
pyinstaller --onefile --name "geely_unlock" --distpath "d:\ADB_Unlock\core" --workpath "d:\ADB_Unlock\core\build" --specpath "d:\ADB_Unlock\core" "d:\ADB_Unlock\core\server.py"
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
   python -c "import platform; platform.system = lambda: 'Darwin'; exec(open('d:/ADB_Unlock/core/server.py', encoding='utf-8').read())"
   ```

---

## 4. Часто встречающиеся проблемы и решения

### Проблема: Батник выдает странные ошибки команд на Windows
* **Причина:** Переводы строк `LF` вместо `CRLF` или кириллические символы в коде батника.
* **Решение:** Файл [СТАРТ_Windows.bat](file:///d:/ADB_Unlock/%D0%A1%D0%A2%D0%90%D0%A0%D0%A2_Windows.bat) должен содержать строго переносы `\r\n` (CRLF) и чистый ASCII-текст команд.

### Проблема: Ошибка «Must be root» или пропуск 20-секундного окна
* **Причина:** ГУ загрузилось слишком быстро или сброс был начат до запуска скрипта.
* **Решение:** Повторить сброс до заводских настроек на экране ГУ. Движок находится в бесконечном цикле опроса и автоматически перехватит следующую попытку.

### Проблема: Порт 8765 занят
* **Решение:** Сервер автоматически проверяет порты от 8765 до 8774. Если процесс завис, нажать кнопку «Очистить ADB» в шапке или завершить процесс через диспетчер задач.
