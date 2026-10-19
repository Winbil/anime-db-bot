# anime-db-bot

Telegram-бот для поиска и объединения информации об аниме из нескольких внешних баз данных. Сейчас подключён Shikimori GraphQL.

## Структура

```text
anime-db-bot/
├── bots/
│   ├── common.py      # общие Telegram-хендлеры и отправка сообщений
│   ├── official.py    # официальный api.telegram.org
│   └── tgapi.py       # custom/self-hosted telegram-bot-api
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

Режим выбирается через `.env`. В обоих режимах подробные карточки аниме отправляются через `sendRichMessage`, который поддерживает до 32768 UTF-8 символов. Если rich message не удалось отправить, бот автоматически откатывается на обычный `sendMessage` с разбиением текста.

### Официальный Bot API

```env
TELEGRAM_BOT_API_URL=
```

Запускается `bots.official` и используется официальный `https://api.telegram.org`.

### Свой telegram-bot-api

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=true
```

Запускается `bots.tgapi` и запросы идут через указанный custom/self-hosted Bot API endpoint.

`TELEGRAM_BOT_API_LOCAL=true` нужен только если сам сервер `telegram-bot-api` запущен с `--local`.

## Источники

Сейчас:

- Shikimori — `sources/shikimori.py`

Планируются:

- AniList / AniDB
- AnimeThemes
- SkipDB
