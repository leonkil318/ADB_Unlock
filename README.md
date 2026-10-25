# Geely ADB Unlock Master 🚀

Универсальное кроссплатформенное решение «в один клик» для постоянной разблокировки отладки по ADB, отключения ограничений установки сторонних приложений (Parrot certificates, AutoInstallVerifier) и интеграции с веб-установщиком GeelyTune на автомобилях Geely (в частности Geely EX5 EM-i с прошивками 2.1.4.5+ / Flyme Auto / Ecarx).

---

## 📦 Готовые автономные сборки (Скачать в один клик)

Для работы **не требуется** устанавливать Python или настраивать среду. Скачайте архив под вашу систему со страницы **[Релизы (Releases)](https://github.com/leonkil318/ADB_Unlock/releases/latest)**:

| Платформа | Файл загрузки | Инструкция |
| :--- | :--- | :--- |
| **Windows 10/11** | [⬇️ **GeelyUnlock-Windows.zip**](https://github.com/leonkil318/ADB_Unlock/releases/latest/download/GeelyUnlock-Windows.zip) | Распаковать архив и запустить `СТАРТ_Windows.bat` |
| **macOS (Apple Silicon / Intel)** | [⬇️ **GeelyUnlock-macOS.tar.gz**](https://github.com/leonkil318/ADB_Unlock/releases/latest/download/GeelyUnlock-macOS.tar.gz) | Распаковать и запустить `СТАРТ_Mac.command` |
| **Linux (Ubuntu / Debian / Fedora)** | [⬇️ **GeelyUnlock-Linux.tar.gz**](https://github.com/leonkil318/ADB_Unlock/releases/latest/download/GeelyUnlock-Linux.tar.gz) | Распаковать и запустить `./СТАРТ_Linux.sh` |

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

### ⚡ Сценарий 1: Экспресс-снятие защиты (После обновления у ОД до 2.1.4.5+)
> **Разборка салона и перемычка НЕ ТРЕБУЮТСЯ!**  
> Если ADB уже открывался ранее, VHAL-порт сохранен. Скрипт мгновенно отключает защиту Parrot certificates (`ro.vendor.ecarx.app_verify=false`), отключает `com.ecarx.xsfinstallverifier` и устанавливает `Geely-ADB-Toggle-1.1.0.apk`.

### 🔌 Сценарий 2: Полная разблокировка с нуля (С перемычкой и сбросом настроек)
1. **Шаг 1: Аппаратная перемычка:**
   - Снятие накладки DHU, установка перемычки во 2-е пины сверху нижней колодки.
   - Подключение ноутбука через USB-A ↔ USB-A в сервисный порт тоннеля.
2. **Шаг 2: Сброс настроек (Factory Reset):**
   - Сброс настроек на экране ГУ. Автоматический перехват 20-секундного окна root-доступа и фиксация VHAL (`USB_SWITCH=0`).
3. **Шаг 3: Снятие перемычки и перезагрузка:**
   - Извлечение перемычки, перезагрузка ГУ и проверка постоянного ADB.
4. **Шаг 4: Снятие ограничений установки:**
   - Отключение верификаторов Parrot / AutoInstallVerifier и установка переключателя.
5. **Шаг 5: GeelyTune:**
   - Переход в браузер к веб-установщику [GeelyTune](https://geelytune.github.io).

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
