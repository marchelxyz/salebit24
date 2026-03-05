# salebit24 — CRM → Telegram Notifier

Telegram-бот для уведомлений о новых контактах из CRM. Отправляет название, имя, телефон. Телефон оформлен как кликабельная ссылка — при нажатии открывается звонок в Mango Office или системный дозвон.

## Требования

- Python 3.11+
- Аккаунт [Railway](https://railway.app)
- Telegram-бот (создать через [@BotFather](https://t.me/BotFather))

## Быстрый старт

### 1. Получение данных

- **TELEGRAM_BOT_TOKEN** — токен от @BotFather
- **TELEGRAM_CHAT_ID** — ID чата/группы для уведомлений (можно узнать через @userinfobot или @getidsbot)
- **MANGO_CALL_URL_TEMPLATE** (опционально) — URL-шаблон Mango Office для звонка. В личном кабинете Mango Office: Интеграции → Вебхуки → Исходящие звонки. URL должен содержать плейсхолдер `{phone}` (номер подставится в формате `79991234567`)

### 2. Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
# опционально: export MANGO_CALL_URL_TEMPLATE="https://...&TelNumbr={phone}"

uvicorn src.main:app --reload --port 8000
```

### 3. Развёртывание на Railway

```bash
export TELEGRAM_BOT_TOKEN="ваш_токен"
export TELEGRAM_CHAT_ID="ваш_chat_id"
# опционально:
# export MANGO_CALL_URL_TEMPLATE="https://integration-webhook.mango-office.ru/...&TelNumbr={phone}"

chmod +x deploy.sh
./deploy.sh
```

Скрипт `deploy.sh`:

1. Проверяет/устанавливает Railway CLI
2. Выполняет авторизацию
3. Задаёт переменные окружения
4. Выполняет `railway up`

После деплоя Railway выдаст публичный URL (например `https://xxx.up.railway.app`).

### 4. Настройка CRM

Направьте вебхук CRM на:

```
POST https://ваш-url.up.railway.app/webhook/crm
Content-Type: application/json

{
  "name": "Иван Иванов",
  "phone": "+7 999 123-45-67",
  "title": "Заявка с сайта"
}
```

- **name** — обязательно  
- **phone** — обязательно  
- **title** — необязательно (название/источник)

## Примеры для разных CRM

### Bitrix24 — исходящие вебхуки (рекомендуется)

Бот поддерживает **исходящие вебхуки** Bitrix24: при добавлении контакта или лида Bitrix24 сам вызывает ваш сервер.

#### Шаг 1: Создание локального приложения

1. Откройте **Приложения** → **Разработчикам**
2. Вкладка **Готовые сценарии** → **Другое** → **Локальное приложение**
3. Создайте приложение с правами доступа **crm**

> Создавать локальные приложения может только администратор портала. Нужна подписка на [Битрикс24 Маркетплейс](https://www.bitrix24.ru/apps/subscribe.php).

#### Шаг 2: Регистрация событий

В инсталляторе приложения зарегистрируйте обработчики через `event.bind`:

| Параметр | Значение |
|----------|----------|
| **event** | `OnCrmContactAdd` |
| **handler** | `https://ваш-url.up.railway.app/webhook/bitrix24` |

Для уведомлений о **лидах** добавьте второй обработчик:

| Параметр | Значение |
|----------|----------|
| **event** | `OnCrmLeadAdd` |
| **handler** | `https://ваш-url.up.railway.app/webhook/bitrix24` |

#### Какие события выбрать

- **OnCrmContactAdd** — новый контакт в CRM
- **OnCrmLeadAdd** — новый лид (заявка)

Выберите те, что нужны. Один и тот же URL (`/webhook/bitrix24`) обрабатывает оба типа.

#### Шаг 3: Установка

Установите приложение на портал. После этого Bitrix24 начнёт отправлять POST-запросы на ваш URL при каждом добавлении контакта/лида.

---

**Альтернатива — ручной вебхук**

Если локальное приложение недоступно, в роботе «Вебхук» (Автоматизация) укажите `https://ваш-url/webhook/crm` и передайте поля:

- `name` — из `NAME` / `LAST_NAME` контакта
- `phone` — из телефона
- `title` — из `SOURCE` или `TITLE`

### AmoCRM

В триггере или интеграции при создании контакта отправляйте POST на `/webhook/crm` с теми же полями.

## Mango Office

Если задан `MANGO_CALL_URL_TEMPLATE`, ссылка на телефон в Telegram откроет исходящий звонок в Mango Office. Пример шаблона:

```
https://integration-webhook.mango-office.ru/webhookapp/common?code=...&Source=Other&API_key=...&Action=Callback&EmployeeNUM=...&TelNumbr={phone}
```

Значения берутся в личном кабинете Mango Office в разделе интеграций.
