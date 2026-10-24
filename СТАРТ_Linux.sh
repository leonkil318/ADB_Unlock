#!/usr/bin/env bash
cd "$(dirname "$0")"
clear
echo "==================================================="
echo "    Запуск Мастера разблокировки Geely ADB..."
echo "==================================================="
echo ""

chmod +x "core/bin/adb"* 2>/dev/null
chmod +x "core/unlock-hu.sh" 2>/dev/null

if command -v python3 >/dev/null 2>&1; then
    python3 "core/server.py"
elif command -v python >/dev/null 2>&1; then
    python "core/server.py"
else
    echo "ОШИБКА: Python 3 не найден в системе."
    echo "Пожалуйста, установите Python 3 (например: sudo apt install python3)."
    read -p "Нажмите Enter для выхода..."
fi
