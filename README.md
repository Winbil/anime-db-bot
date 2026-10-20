# anime-db-bot

Telegram-бот для поиска аниме и объединения данных из нескольких баз в одну интерактивную карточку.

Главный принцип проекта: **поиск и источники метаданных — разные слои**. Поисковые сервисы находят аниме и приводят результат к MAL ID, а источники данных получают уже выбранный MAL ID и не занимаются текстовым поиском.

## Что сейчас подключено

### Поисковики

- **Shikimori Search** — особенно полезен для русских названий;
- **MyAnimeList API v2** — хороший международный поиск и канонический MAL ID.

Оба поисковика вызываются параллельно. Результаты объединяются **строго по MAL ID**.

### Источники метаданных

- **Shikimori**;
- **AniList**.

Они вызываются только после того, как пользователь выбрал конкретное аниме.

## Команды

- `/start` — режим Telegram API, поисковики и источники;
- `/ping` — проверка работы бота;
- `/anime <название>` — поиск аниме.

Например:

```text
/anime о моем перерождении в слизь
```

или:

```text
/anime Tensei Shitara Slime Datta Ken
```

---

# Архитектура

```text
anime-db-bot/
├── core/
│   ├── contracts.py
│   └── models.py
│
├── search/
│   ├── registry.py
│   └── providers/
│       ├── __init__.py
│       ├── mal.py
│       └── shikimori.py
│
├── services/
│   ├── search.py
│   └── aggregator.py
│
├── sources/
│   ├── registry.py
│   ├── shikimori.py
│   └── anilist.py
│
├── bots/
│   ├── common.py
│   ├── official.py
│   └── tgapi.py
│
├── .env.example
├── requirements.txt
├── start.sh
└── README.md
```

## Поток запроса

```text
/anime <текст>
       │
       ▼
  SearchService
       │
       ├──────────────► ShikimoriSearchProvider
       │
       └──────────────► MALSearchProvider
                         │
                         ▼
              результаты с MAL ID
                         │
                         ▼
             объединение по MAL ID
                         │
                         ▼
                  SearchCandidate
                         │
              пользователь выбирает
                         │
                         ▼
                      MAL ID
                 + известные cross-ID
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      ShikimoriSource          AniListSource
             │                       │
             └───────────┬───────────┘
                         ▼
                  AnimeAggregator
                         │
                         ▼
                  AggregatedAnime
                         │
                         ▼
                Telegram rich card
```

---

# Поиск

Поиск расположен отдельно от источников данных:

```text
search/
```

Источники из `sources/` **не должны реализовывать текстовый поиск**.

## `search/providers/shikimori.py`

Отвечает только за поиск через Shikimori.

Он получает пользовательский текст и возвращает нормализованные результаты:

```text
русское/romaji/english название
MAL ID
Shikimori ID
год
оценка
синонимы
```

Shikimori особенно полезен для запросов на русском языке.

## `search/providers/mal.py`

Отвечает только за MyAnimeList API v2.

Он возвращает:

```text
MAL ID
название
альтернативные названия
год
оценку MAL
```

Для публичного MAL API нужен только `MAL_CLIENT_ID`. OAuth/access token для поиска не нужен.

## `search/registry.py`

Единственная точка, где включаются поисковики:

```python
return (
    ShikimoriSearchProvider(),
    MALSearchProvider(),
)
```

Позже сюда можно добавить локальный индекс ID/названий без изменения Telegram-слоя или metadata sources.

---

# SearchService

Файл:

```text
services/search.py
```

SearchService:

1. нормализует запрос;
2. параллельно вызывает все search providers;
3. не ломает весь поиск при падении одного провайдера;
4. отбрасывает результаты без MAL ID;
5. объединяет совпадения строго по MAL ID;
6. объединяет aliases, cross-ID и оценки;
7. выбирает удобное отображаемое название;
8. кеширует результат.

## Выбор названия

Если запрос содержит кириллицу, предпочтение отдаётся названию Shikimori.

Например:

```text
/anime о моем перерождении в слизь
```

в выдаче предпочтительно будет:

```text
О моём перерождении в слизь
```

Для латиницы предпочтение отдаётся MyAnimeList.

## Объединение

Например:

```text
Shikimori
MAL: 37430
Shikimori: 39607
О моём перерождении в слизь

MyAnimeList
MAL: 37430
Tensei Shitara Slime Datta Ken
```

превращается в один `SearchCandidate`:

```text
MAL: 37430
Shikimori: 39607
aliases: ...
scores: ...
```

MAL ID является основным ключом дедупликации.

## Частичный сбой

Если MAL временно недоступен, но Shikimori работает, поиск продолжает работать.

Если Shikimori недоступен, но MAL работает — аналогично.

Telegram может показать:

```text
Недоступны поисковики: MyAnimeList
```

но рабочие результаты всё равно будут доступны.

---

# Кэш поиска

Повторные одинаковые запросы кешируются в RAM процесса.

По умолчанию:

```env
SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
```

`21600` секунд = 6 часов.

Ключ кеша включает:

```text
query + page + page_size
```

Поэтому повторный запрос той же страницы не обращается заново к Shikimori и MAL до истечения TTL.

Отключить кеш:

```env
SEARCH_CACHE_TTL_SECONDS=0
```

После перезапуска процесса RAM-кэш очищается.

Позже его можно заменить Redis/SQLite без изменения провайдеров поиска.

---

# Metadata sources

Источники находятся в:

```text
sources/
```

Они не получают пользовательскую строку поиска.

Общий контракт примерно такой:

```python
async def get_details(
    mal_id: str,
    known_ids: dict[str, str],
) -> AnimeRecord | None:
    ...
```

`known_ids` содержит cross-ID, которые уже нашли search providers.

Например:

```python
{
    "mal": "37430",
    "shikimori": "39607",
}
```

Это позволяет не выполнять повторный текстовый поиск внутри источников.

## ShikimoriSource

Shikimori не всегда позволяет удобно получить запись напрямую только по MAL ID.

Поэтому `ShikimoriSearchProvider` заранее сохраняет пару:

```text
MAL ID ↔ Shikimori ID
```

После выбора результата `ShikimoriSource` получает уже известный Shikimori ID, загружает подробности по нему и обязательно сверяет `malId`.

Никакого fallback-поиска по названию внутри `sources/shikimori.py` нет.

## AniListSource

AniList поддерживает lookup:

```graphql
Media(idMal: ...)
```

поэтому получает выбранный MAL ID напрямую.

AniList **не используется для текстового поиска**, поэтому его rate limit не тратится на каждый `/anime`.

Он запрашивается только после выбора конкретного результата.

---

# Агрегатор

Файл:

```text
services/aggregator.py
```

`AnimeAggregator` получает выбранный `SearchCandidate`, извлекает MAL ID и уже найденные cross-ID и параллельно обращается к metadata sources.

В одну карточку объединяются:

- названия;
- синонимы;
- MAL/Shikimori/AniList ID;
- тип;
- статус;
- количество серий;
- длительность;
- даты показа;
- следующий эпизод;
- жанры;
- студии;
- лицензиаты;
- оценки по источникам;
- описания;
- постеры;
- ссылки;
- команда;
- сэйю.

Оценки не смешиваются:

```text
Оценки:
MyAnimeList: 8.14
Shikimori: 8.31
AniList: 8.2
```

---

# Карточка Telegram

Основная информация разбита на смысловые блоки:

```text
Название

Основное:
Тип: TV
Статус: вышло
Серии: 24/24
Длительность серии: 23 мин.
Возрастной рейтинг: PG-13

Выход:
Сезон: Осень 2018
Начало/Конец показа: 2018-10-02/2019-03-19

Производство:
Жанры: ...
Студии: ...

Оценки:
Shikimori: ...
AniList: ...
MyAnimeList: ...

Источники:
Базы данных: Shikimori, AniList
ID: MAL: ... | SHIKIMORI: ... | ANILIST: ...
```

Обложка встроена в то же rich message.

Разделы `Описание`, `Все названия`, `Авторы и команда`, `Сэйю` являются callback-ссылками прямо внутри rich message.

Кнопки `← Назад` и `◀️/▶️` остаются обычными inline-кнопками.

---

# Постеры

`AggregatedAnime.posters` содержит постеры, собранные из metadata sources.

Для Shikimori выбирается лучший размер одного постера:

```text
originalUrl
→ main2xUrl
→ mainUrl
→ preview2xUrl
→ previewUrl
```

Для AniList:

```text
extraLarge
→ large
→ medium
```

Если источники дадут разные реальные обложки, Telegram-слой может показать slideshow.

---

# MyAnimeList Client ID

MAL Client ID теперь **рекомендуется, но не является обязательным для запуска**, потому что Shikimori Search способен работать самостоятельно.

Чтобы включить MAL Search полностью:

1. войди в MyAnimeList;
2. открой `https://myanimelist.net/apiconfig`;
3. создай API application;
4. скопируй Client ID;
5. добавь его в `.env`.

```env
MAL_CLIENT_ID=your_client_id
MAL_API_URL=https://api.myanimelist.net/v2
```

Client Secret и OAuth access token для публичного поиска не нужны.

Если `MAL_CLIENT_ID` пустой, `start.sh` выводит предупреждение, но бот продолжает запускаться и может искать через Shikimori.

---

# Конфигурация

Пример `.env`:

```env
BOT_TOKEN=

TELEGRAM_BOT_API_URL=
TELEGRAM_BOT_API_LOCAL=false

MAL_CLIENT_ID=
MAL_API_URL=https://api.myanimelist.net/v2

SHIKIMORI_API_URL=https://shikimori.io/api/graphql
SHIKIMORI_SITE_URL=https://shikimori.io

SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500

ANILIST_API_URL=https://graphql.anilist.co
ANILIST_ACCESS_TOKEN=
ANILIST_PEOPLE_MAX_PAGES=4
```

---

# Telegram API

Пустой:

```env
TELEGRAM_BOT_API_URL=
```

использует официальный `api.telegram.org` через `bots.official`.

Свой сервер:

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=true
```

использует `bots.tgapi`.

В обоих режимах карточки используют `sendRichMessage` с fallback на обычные сообщения.

---

# Установка

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip tmux git
```

Клонирование:

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
cp .env.example .env
nano .env
./start.sh
```

`BOT_TOKEN` обязателен.

`MAL_CLIENT_ID` рекомендуется, но без него остаётся Shikimori Search.

---

# start.sh

Скрипт:

1. проверяет структуру проекта;
2. создаёт/проверяет `.venv`;
3. устанавливает зависимости;
4. выполняет `pip check`;
5. проверяет imports;
6. проверяет wiring search providers и metadata sources;
7. проверяет `BOT_TOKEN`;
8. предупреждает, если MAL Client ID отсутствует;
9. выбирает Telegram transport;
10. запускает бота в tmux.

Логи:

```bash
tail -f logs/bot.log
```

Подключиться к tmux:

```bash
tmux attach -t anime-db-bot
```

---

# Добавление поисковика

Новый поисковик добавляется в:

```text
search/providers/
```

Он должен вернуть `SearchPage` с результатами, содержащими MAL ID.

После этого он регистрируется в:

```text
search/registry.py
```

Metadata sources менять не требуется.

## Будущий локальный индекс

Позже планируется отдельный локальный search provider с базой соответствий и названий:

```text
MAL ID
Shikimori ID
AniList ID
AniDB ID
русские названия
romaji
english
japanese
синонимы
```

Он сможет работать перед внешними API и уменьшит количество сетевых запросов.

Это отдельный будущий этап; текущая архитектура уже позволяет добавить его без переделки `sources/` или Telegram-слоя.

---

# Добавление metadata source

Новый источник создаётся в:

```text
sources/<name>.py
```

и реализует общий `AnimeSource`.

Он не должен выполнять пользовательский текстовый поиск.

После этого адаптер добавляется только в:

```text
sources/registry.py
```

---

# Главный принцип

```text
search/providers/  → ищут и возвращают MAL ID + cross-ID
services/search.py → объединяет выдачу по MAL ID
sources/           → получают ID и возвращают нормализованные данные
services/aggregator.py → объединяет данные
bots/              → только Telegram UI
```

Это позволяет отдельно отлаживать поиск, конкретные базы и Telegram-интерфейс и не тратить лимиты metadata APIs на обычный текстовый поиск.
