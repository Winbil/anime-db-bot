# anime-db-bot

Минимальный Telegram-бот для поиска информации об аниме. Первая версия использует Shikimori GraphQL как источник данных.

## Сейчас умеет

- `/start` — показать краткую справку
- `/ping` — проверить, что бот запущен
- `/anime <название>` — найти аниме в Shikimori и показать основную информацию

## Требования

- Python 3.11+
- Telegram-бот, созданный через BotFather

## Запуск

```bash
git clone https://github.com/Winbil/anime-db-bot.git
cd anime-db-bot
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Установи зависимости:

```bash
pip install -r requirements.txt
```

Создай `.env` из примера:

```bash
cp .env.example .env
```

На Windows можно просто скопировать `.env.example` в `.env` вручную.

Минимальная конфигурация:

```env
BOT_TOKEN=123456:telegram_bot_token
```

После этого:

```bash
python bot.py
```

## Свой Telegram Bot API сервер

По умолчанию бот использует официальный `https://api.telegram.org`.

Если рядом запущен собственный `telegram-bot-api`, укажи его базовый адрес:

```env
BOT_TOKEN=123456:telegram_bot_token
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=false
```

Если сам `telegram-bot-api` запущен с флагом `--local`, выставь:

```env
TELEGRAM_BOT_API_LOCAL=true
```

Если `TELEGRAM_BOT_API_URL` оставить пустым, никаких дополнительных настроек не требуется — будет использован официальный Telegram Bot API.

## Источники

Сейчас подключён только Shikimori. Остальные источники будут добавляться постепенно, когда появится работающая база проекта.

Планируемые источники: AniList/AniDB, AnimeThemes и SkipDB.
