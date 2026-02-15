#!/bin/bash
# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

print_color() { echo -e "${2}${1}${NC}"; }

print_header() {
    echo ""
    print_color "═══════════════════════════════════════════════════════════════════════════════" "$CYAN"
    print_color "  $1" "$CYAN"
    print_color "═══════════════════════════════════════════════════════════════════════════════" "$CYAN"
    echo ""
}

# Проверка Python
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_color "❌ Python3 не установлен!" "$RED"
        exit 1
    fi
    print_color "✅ Python3: $(python3 --version)" "$GREEN"
}

# Проверка pip
check_pip() {
    if ! command -v pip3 &> /dev/null; then
        print_color "❌ pip3 не установлен!" "$RED"
        exit 1
    fi
    print_color "✅ pip3 найден" "$GREEN"
}

# Проверка .env
check_env() {
    if [ ! -f ".env" ]; then
        print_color "⚠️  Файл .env не найден!" "$YELLOW"
        read -p "Введите токен бота: " token
        echo "BOT_TOKEN=$token" > .env
        print_color "✅ Файл .env создан" "$GREEN"
    fi
}

# Установка зависимостей
install_deps() {
    print_color "📦 Установка зависимостей..." "$YELLOW"
    pip3 install --upgrade pip
    pip3 install pyTelegramBotAPI psycopg2-binary requests schedule pytest pytest-cov python-dotenv
    print_color "✅ Зависимости установлены" "$GREEN"
}

# Unit-тесты
run_unit_tests() {
    print_color "🧪 Запуск unit-тестов..." "$BLUE"
    if [ -f "tests/test_unit.py" ]; then
        python3 -m pytest tests/test_unit.py -v
    else
        print_color "⚠️  Unit-тесты не найдены" "$YELLOW"
    fi
}

# Интеграционные тесты
run_integration_tests() {
    print_color "🔄 Запуск интеграционных тестов..." "$PURPLE"
    if [ -f "tests/test_integration.py" ]; then
        python3 -m pytest tests/test_integration.py -v -s
    else
        print_color "⚠️  Интеграционные тесты не найдены" "$YELLOW"
    fi
}

# Запуск бота
run_app() {
    print_color "🚀 Запуск бота..." "$CYAN"
    if [ -f "bot.py" ]; then
        python3 bot.py
    else
        print_color "❌ Файл bot.py не найден!" "$RED"
        exit 1
    fi
}

# Главная функция
do_everything() {
    print_header "ШАГ 1: ПРОВЕРКА СИСТЕМЫ"
    check_python
    check_pip
    check_env
    
    print_header "ШАГ 2: УСТАНОВКА ЗАВИСИМОСТЕЙ"
    install_deps
    
    print_header "ШАГ 3: UNIT-ТЕСТЫ"
    run_unit_tests
    
    print_header "ШАГ 4: ИНТЕГРАЦИОННЫЕ ТЕСТЫ"
    run_integration_tests
    
    print_header "ШАГ 5: ЗАПУСК ПРИЛОЖЕНИЯ"
    run_app
}

# Запуск
do_everything
