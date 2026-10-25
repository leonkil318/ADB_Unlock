# Geely ADB Unlock Master 🚀

Универсальное кроссплатформенное решение «в один клик» для постоянной разблокировки отладки по ADB, отключения ограничений установки сторонних приложений (Parrot certificates, AutoInstallVerifier) и интеграции с веб-установщиком GeelyTune на автомобилях Geely (в частности Geely EX5 EM-i с прошивками 2.1.4.5+ / Flyme Auto / Ecarx).

---

## 📦 Готовые автономные сборки (Скачать в один клик)

Для работы **не требуется** устанавливать Python или настраивать среду. Скачайте один файл под вашу систему со страницы **[Релизы (Releases)](https://github.com/leonkil318/ADB_Unlock/releases/latest)**:

| Платформа | Одиночный файл программы | Как запускать |
| :--- | :--- | :--- |
| **Windows 10/11** | [⬇️ **GeelyUnlock.exe**](https://github.com/leonkil318/ADB_Unlock/releases/latest/download/GeelyUnlock.exe) | Двойной клик по скачанному `GeelyUnlock.exe` |
| **macOS (Apple Silicon / Intel)** | [⬇️ **GeelyUnlock-macOS**](https://github.com/leonkil318/ADB_Unlock/releases/latest/download/GeelyUnlock-macOS) | `chmod +x GeelyUnlock-macOS` и запуск |
| **Linux (Ubuntu / Debian / Fedora)** | [⬇️ **GeelyUnlock-Linux**](https://github.com/leonkil318/ADB_Unlock/releases/latest/download/GeelyUnlock-Linux) | `chmod +x GeelyUnlock-Linux` и запуск |

---

## ⚡ Быстрый старт из исходников

Если вы склонировали весь репозиторий:

### Windows
Запустите файл:
```text
СТАРТ_Windows.bat
```
*(Не требует Python — используется готовый автономный бинарник `core/geely_unlock.exe`).*

### macOS
Запустите файл:
```bash
СТАРТ_Mac.command
```
*(Или в терминале: `./СТАРТ_Mac.command`)*

### Linux
Запустите файл:
```bash
СТАРТ_Linux.sh
```
*(Или в терминале: `./СТАРТ_Linux.sh`)*

---

## 📋 Сценарии работы

### ⚡ Сценарий 1: Экспресс-снятие защиты (ОД 2.1.4.5+)
> **Перемычка НЕ ТРЕБУЕТСЯ!**  
> Если постоянный ADB уже был открыт ранее, скрипт мгновенно отключает защиту Parrot certificates (`ro.vendor.ecarx.app_verify=false`), отключает системный `com.ecarx.xsfinstallverifier` и устанавливает `Geely-ADB-Toggle-1.1.0.apk`.

### 🔌 Сценарий 2: Первоначальная разблокировка ADB (через Factory Reset)
1. **Шаг 1: Подключение:**
   - Подключение ноутбука через кабель USB-A ↔ USB-A к сервисному порту автомобиля (при установленной перемычке).
2. **Шаг 2: Сброс настроек (Factory Reset):**
   - Нажатие «Сброс до заводских настроек» на экране ГУ. Автоматический перехват 20-секундного сервисного окна и программная фиксация VHAL (`USB_SWITCH=0`).
3. **Шаг 3: Снятие перемычки и перезагрузка:**
   - Извлечение перемычки, перезагрузка ГУ и подтверждение постоянного ADB в штатном режиме.
4. **Шаг 4: Снятие ограничений установки:**
   - Отключение верификаторов Parrot / AutoInstallVerifier и установка переключателя ADB-Toggle.
5. **Шаг 5: GeelyTune:**
   - Открытие веб-установщика [GeelyTune](https://geelytune.github.io) в браузере.

---

## 📁 Структура проекта

```text
├── СТАРТ_Windows.bat        # Запуск для Windows
├── СТАРТ_Mac.command        # Запуск для macOS
├── СТАРТ_Linux.sh           # Запуск для Linux
├── README.md                # Документация проекта
├── core/                    # Внутренние компоненты
│   ├── main.py              # Точка входа TUI-приложения
│   ├── engine.py            # Движок бизнес-логики (ADB, VHAL, Parrot)
│   ├── tui.py               # Zero-Dependency терминальный интерфейс
│   ├── geely_unlock.exe     # Автономный бинарник для Windows
│   ├── bin/                 # Встроенные бинарники Android Debug Bridge
│   │   ├── adb.exe          # Google ADB для Windows (+ DLL)
│   │   ├── adb-darwin       # ADB для macOS (Universal)
│   │   └── adb-linux        # ADB для Linux (x86_64)
│   ├── unlock-hu.sh         # Скрипт снятия системных ограничений ГУ
│   └── Geely-ADB-Toggle...  # APK системного переключателя
└── .agents/                 # AI-правила и база знаний разработки
```

---

## ⚠️ Предупреждение (Disclaimer)

Все действия выполняются вами на собственный страх и риск. Модификация системных настроек автомобиля может повлиять на гарантийные обязательства.
