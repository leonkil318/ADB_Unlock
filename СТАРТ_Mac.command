#!/usr/bin/env bash
cd "$(dirname "$0")"
clear
echo "==================================================="
echo "    Запуск Мастера разблокировки Geely ADB..."
echo "==================================================="
echo ""

chmod +x "core/bin/adb"* 2>/dev/null
chmod +x "core/unlock-hu.sh" 2>/dev/null

if [ -f "core/geely_unlock" ]; then
    chmod +x "core/geely_unlock"
    ./core/geely_unlock
    exit 0
elif [ -f "core/geely_unlock_mac" ]; then
    chmod +x "core/geely_unlock_mac"
    ./core/geely_unlock_mac
    exit 0
fi

if command -v python3 >/dev/null 2>&1; then
    python3 "core/main.py"
elif command -v python >/dev/null 2>&1; then
    python "core/main.py"
else
    echo "ОШИБКА: Python 3 не найден в системе."
    echo "Пожалуйста, установите Python 3 для запуска."
    read -p "Нажмите Enter для выхода..."
fi
