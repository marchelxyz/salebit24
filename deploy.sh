#!/usr/bin/env bash
#
# Скрипт развёртывания CRM → Telegram бота на Railway.
# Использование: ./deploy.sh
#
# Перед запуском задайте переменные окружения:
#   export TELEGRAM_BOT_TOKEN="..."
#   export TELEGRAM_CHAT_ID="..."
#   export MANGO_CALL_URL_TEMPLATE="..."  # опционально
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== CRM Telegram Notifier — развёртывание на Railway ==="

# Проверка Railway CLI
if ! command -v railway &> /dev/null; then
    echo "Railway CLI не найден. Установка..."
    if command -v npm &> /dev/null; then
        npm install -g @railway/cli
    else
        echo "Установите Railway CLI вручную:"
        echo "  npm i -g @railway/cli"
        echo "  или: https://docs.railway.app/guides/cli"
        exit 1
    fi
fi

# Авторизация
if ! railway whoami &> /dev/null; then
    echo "Требуется авторизация в Railway..."
    railway login
fi

# Связь с проектом (если ещё не связано)
if ! railway status &> /dev/null 2>&1; then
    echo "Связывание с проектом Railway..."
    railway init || railway link
fi

# Установка переменных окружения
echo "Проверка переменных окружения..."
REQUIRED=("TELEGRAM_BOT_TOKEN" "TELEGRAM_CHAT_ID")
for var in "${REQUIRED[@]}"; do
    if [[ -z "${!var}" ]]; then
        echo "ВНИМАНИЕ: $var не задан."
        echo "Задайте перед деплоем: export $var=\"ваше_значение\""
        read -r -p "Ввести $var сейчас? (y/n): " ans
        if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
            read -r -p "$var: " val
            railway variables set "$var=$val"
        else
            echo "Развёртывание невозможно без $var."
            exit 1
        fi
    else
        railway variables set "$var=${!var}"
    fi
done

if [[ -n "$MANGO_CALL_URL_TEMPLATE" ]]; then
    railway variables set "MANGO_CALL_URL_TEMPLATE=$MANGO_CALL_URL_TEMPLATE"
    echo "MANGO_CALL_URL_TEMPLATE установлен (ссылка откроется в Mango Office)"
else
    echo "MANGO_CALL_URL_TEMPLATE не задан — телефон будет в формате tel:+7..."
fi

# Деплой
echo ""
echo "Запуск деплоя..."
railway up

echo ""
echo "=== Готово ==="
echo "После деплоя получите публичный URL в Railway и настройте вебхук CRM:"
echo "  POST <ваш-url>/webhook/crm"
echo "  Body: {\"name\": \"Иван\", \"phone\": \"+79991234567\", \"title\": \"Сайт\"}"
echo ""
