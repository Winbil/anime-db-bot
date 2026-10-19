# anime-db-bot

Telegram-бот для поиска и объединения информации об аниме из нескольких внешних баз данных. Сейчас подключён Shikimori GraphQL.

## Структура

```text
anime-db-bot/
├── bots/
│   ├── common.py      # общие Telegram-хендлеры и отправка сообщений
│   ├── official.py    # официальный Bot API + sendMessage
│   └── tgapi.py       # custom telegram-bot-api + sendRichMessage
├── sources/
│   └── shikimori.py   # всё, что относится к Shikimori
├── start.sh
├── requirements.txt
└── .env.example
```

Новые источники нужно добавлять отдельными модулями в `sources/`, например `anilist.py`, `anidb.py`, `animethemes.py`, `skipdb.py`.

## Команды

- `/start` — краткая справка и текущий Telegram-режим
- `/ping` — проверить, что бот работает
- `/anime <название>` — найти аниме в Shikimori

## Быстрый запуск на Linux

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
cp .env.example .env
nano .env
./start.sh
```

`start.sh` сам создаёт `.venv`, устанавливает зависимости, проверяет импорты и запускает бота в tmux-сессии `anime-db-bot`.

Если бот уже запущен, скрипт спросит, нужно ли его перезапустить.

## Telegram API режимы

Режим выбирается через `.env`.

### Официальный Bot API

```env
TELEGRAM_BOT_API_URL=
```

Запускается `bots.official`. Используется обычный `sendMessage`; длинный текст автоматически разбивается, чтобы не превышать лимит 4096 символов.

### Свой telegram-bot-api

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=true
```

Запускается `bots.tgapi`. Для подробной карточки используется `sendRichMessage`, который поддерживает до 32768 UTF-8 символов. Если локальный Bot API слишком старый и не поддерживает этот метод, бот автоматически откатывается на обычные `sendMessage` с разбиением.

`TELEGRAM_BOT_API_LOCAL=true` нужен только если сам сервер `telegram-bot-api` запущен с `--local`.

## Источники

Сейчас:

- Shikimori — `sources/shikimori.py`

Планируются:

- AniList / AniDB
- AnimeThemes
- SkipDB
