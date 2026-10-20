# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких баз данных.

Главная идея проекта: **поиск, источники метаданных и агрегирование — разные слои**.

- поисковики находят аниме и MAL ID;
- metadata sources получают уже выбранный MAL ID и cross-ID;
- `AnimeAggregator` объединяет одинаковые по смыслу поля разных баз без повторений;
- Telegram получает уже готовую `AggregatedAnime` и не знает, откуда пришёл конкретный жанр, студия или дата.

---

# Что подключено

## Поиск

Обычная команда `/anime` использует:

- **Shikimori Search** — особенно полезен для русских названий;
- **MyAnimeList Search** — международный поиск и MAL ID.

Они работают параллельно, а результаты объединяются строго по MAL ID.

Дополнительно есть `/search`, где можно явно выбрать:

- MyAnimeList;
- Shikimori;
- AniList;
- несколько поисковиков одновременно;
- все доступные поисковики.

AniList Search специально не входит в обычный `/anime`, чтобы не расходовать его rate limit без необходимости.

## Metadata sources

После выбора аниме агрегатор обращается к:

- **Shikimori**;
- **AniList**;
- **MyAnimeList**.

Источники не отображаются как три независимые карточки. Их данные нормализуются и объединяются.

---

# Команды

```text
/start
/ping
/anime <название>
/search <название>
/search mal <название>
/search shikimori <название>
/search anilist <название>
/search all <название>
/search mal,shikimori <название>
```

Примеры:

```text
/anime о моем перерождении в слизь
/search shikimori о моем перерождении в слизь
/search mal slime
/search mal,anilist slime
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
│       ├── mal.py
│       ├── shikimori.py
│       └── anilist.py
│
├── services/
│   ├── search.py
│   └── aggregator.py
│
├── sources/
│   ├── registry.py
│   ├── mal.py
│   ├── shikimori.py
│   └── anilist.py
│
├── bots/
│   ├── common.py
│   ├── search_ui.py
│   ├── runner.py
│   ├── official.py
│   └── tgapi.py
│
├── .env.example
├── requirements.txt
├── start.sh
└── README.md
```

---

# Полный поток `/anime`

```text
/anime <текст>
       │
       ▼
  SearchService
       │
       ├────────► ShikimoriSearchProvider
       │
       └────────► MALSearchProvider
                       │
                       ▼
              SearchCandidate[]
                       │
              merge by MAL ID
                       │
                       ▼
             пользователь выбирает
                       │
                       ▼
          MAL ID + известные cross-ID
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
      Shikimori    AniList       MAL
        Source      Source      Source
            │          │          │
            └──────────┼──────────┘
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

# Search providers

Поисковые адаптеры находятся только в:

```text
search/providers/
```

Они отвечают за поиск, но не за подробную карточку.

Общий контракт:

```python
async def search(
    query: str,
    *,
    page: int,
    limit: int,
) -> SearchPage:
    ...
```

Каждый найденный элемент приводится к `SearchCandidate`.

Главное требование — наличие MAL ID. Именно MAL ID сейчас является каноническим ключом проекта.

## Shikimori Search

Полезен для русского поиска и дополнительно даёт Shikimori ID.

Например:

```text
MAL: 37430
Shikimori: 39607
О моём перерождении в слизь
```

## MyAnimeList Search

Работает через MAL API v2 и даёт:

- MAL ID;
- canonical title;
- alternative titles;
- год;
- оценку.

Для публичного API нужен `MAL_CLIENT_ID`.

## AniList Search

Доступен через `/search`, но не входит в стандартный `/anime`.

Результаты без `idMal` отбрасываются, потому что дальше система работает через MAL ID.

---

# SearchService

Файл:

```text
services/search.py
```

SearchService:

1. нормализует запрос;
2. параллельно вызывает выбранные search providers;
3. не ломает всю выдачу при сбое одного поисковика;
4. объединяет совпадения строго по MAL ID;
5. объединяет aliases, cross-ID и найденные оценки;
6. предпочитает русское название Shikimori для кириллического запроса;
7. кеширует результаты в RAM.

Пример объединения:

```text
Shikimori
MAL 37430
Shikimori 39607
О моём перерождении в слизь

MyAnimeList
MAL 37430
Tensei Shitara Slime Datta Ken

                ↓

один SearchCandidate
MAL 37430
Shikimori 39607
aliases: ...
```

---

# Кэш поиска

По умолчанию:

```env
SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
```

`21600` секунд = 6 часов.

Повторный одинаковый запрос/страница в пределах TTL не обращается к API повторно.

Отключить:

```env
SEARCH_CACHE_TTL_SECONDS=0
```

Кэш пока находится в RAM процесса и очищается после перезапуска.

---

# Metadata sources

Metadata adapters находятся в:

```text
sources/
```

Они **не выполняют текстовый поиск**.

Контракт:

```python
async def get_details(
    mal_id: str,
    known_ids: dict[str, str],
) -> AnimeRecord | None:
    ...
```

`known_ids` может содержать:

```python
{
    "mal": "37430",
    "shikimori": "39607",
    "anilist": "101280",
}
```

## ShikimoriSource

Получает уже известный Shikimori ID, загружает запись и сверяет её `malId`.

Никакого скрытого повторного поиска по названию в metadata source нет.

## AniListSource

Использует прямой GraphQL lookup:

```graphql
Media(idMal: ...)
```

Поэтому ему достаточно MAL ID.

## MALSource

Использует:

```text
GET /v2/anime/{mal_id}
```

и добавляет в общую модель не только стандартную метадату, но и:

- rank;
- popularity;
- количество пользователей в списках;
- количество поставивших оценку;
- favorites;
- первоисточник;
- broadcast schedule;
- background;
- дополнительные изображения.

Отдельного ключа для MAL metadata не нужно — используется тот же `MAL_CLIENT_ID`.

---

# Семантическое агрегирование

Файл:

```text
services/aggregator.py
```

Главное правило: **источник — это способ получить данные, а не отдельная категория в карточке**.

Например:

```text
Shikimori genres: Action, Adventure
MAL genres:       Action, Adventure, Fantasy
AniList genres:   Adventure, Fantasy
```

Итог:

```text
Жанры: Action, Adventure, Fantasy
```

Никаких трёх отдельных списков жанров.

## Списочные поля

Объединяются без повторений:

- жанры;
- студии;
- лицензиаты;
- первоисточники;
- расписание;
- синонимы;
- постеры;
- external IDs;
- staff;
- сэйю.

Для персонала одинаковый человек объединяется, а его роли дополняются.

## Названия

Для каждой категории выбирается одно основное значение:

```text
russian
romaji
english
japanese
licensed_ru
```

Если другой источник дал другое название той же категории, оно не теряется — уходит в aliases/synonyms.

## Одиночные поля

Для типа, статуса, рейтинга, сезона, дат и похожих полей используется консенсус доступных источников.

Если одинаковое значение дали несколько баз — оно имеет приоритет.

Для количества серий при ничьей выбирается более полное значение.

Для числа уже вышедших серий берётся максимальный доступный прогресс.

## Оценка

Источник-специфичные оценки сохраняются внутренне, но пользователю показывается одна агрегированная оценка:

```text
Средняя оценка: 8.31 (3 источника)
```

Все входные оценки предварительно приводятся источниками к шкале 0–10.

## Описание

Вместо отдельных блоков:

```text
[Shikimori]
...

[AniList]
...

[MAL]
...
```

выбирается наиболее полное непустое описание.

`background` хранится отдельно как дополнительная информация и показывается под описанием.

## Популярность

Поля `rank`, `popularity_rank`, `list_users`, `scoring_users`, `favorites` являются универсальными полями модели.

Сейчас их в основном заполняет MAL, но они не называются `mal_rank` и не привязаны архитектурно к MAL. Если позже другая база сможет дополнить то же поле, агрегатор применит к нему общие правила.

---

# Telegram-карточка

Пример:

```text
О моём перерождении в слизь

Основное:
Тип: TV
Статус: вышло
Серии: 24/24
Длительность серии: 23 мин.
Возрастной рейтинг: PG-13

Выход:
Сезон: Осень 2018
Начало/Конец показа: 2018-10-02/2019-03-19
Расписание: Вторник 23:00

Производство:
Первоисточник: Ранобэ
Жанры: Приключения, Фэнтези, Комедия
Студии: 8bit

Оценка и популярность:
Средняя оценка: 8.31 (3 источника)
Рейтинг: #123
Популярность: #45
В списках пользователей: 1 200 000
Поставили оценку: 800 000
В избранном: 30 000

Источники:
Базы данных: Shikimori, AniList, MyAnimeList
ID: MAL: ... | SHIKIMORI: ... | ANILIST: ...
...
```

Название источника остаётся только там, где оно действительно является частью значения: например URL или внешний ID.

---

# Rich messages

Основная карточка использует `sendRichMessage`.

Постер находится в том же сообщении, что и текст.

Разделы:

- `Описание`;
- `Все названия`;
- `Авторы и команда`;
- `Сэйю`;

реализованы как callback-ссылки внутри rich message.

`← Назад` и пагинация `◀️ / ▶️` остаются обычными inline-кнопками.

Если rich message не проходит, бот использует fallback на обычный `sendMessage`.

---

# Постеры

Каждый source adapter должен возвращать лучшие реальные изображения, а не несколько размеров одного и того же файла.

Агрегатор удаляет точные дубликаты URL.

Если после объединения осталось несколько реальных изображений, Telegram показывает их как rich slideshow.

---

# MyAnimeList Client ID

Чтобы включить MAL Search и MAL metadata:

1. войди в MyAnimeList;
2. открой `https://myanimelist.net/apiconfig`;
3. создай API application;
4. скопируй Client ID;
5. добавь его в `.env`.

```env
MAL_CLIENT_ID=your_client_id
MAL_API_URL=https://api.myanimelist.net/v2
```

Client Secret и OAuth access token для публичного поиска/metadata не нужны.

Если `MAL_CLIENT_ID` пустой, бот всё равно запускается, но MAL Search и MALSource будут недоступны. Shikimori/AniList продолжат работать.

---

# `.env`

Минимум:

```env
BOT_TOKEN=...
```

Рекомендуемый вариант:

```env
BOT_TOKEN=...

TELEGRAM_BOT_API_URL=
TELEGRAM_BOT_API_LOCAL=false

MAL_CLIENT_ID=...
MAL_API_URL=https://api.myanimelist.net/v2

SHIKIMORI_API_URL=https://shikimori.io/api/graphql
SHIKIMORI_SITE_URL=https://shikimori.io

ANILIST_API_URL=https://graphql.anilist.co
ANILIST_ACCESS_TOKEN=
ANILIST_PEOPLE_MAX_PAGES=4

SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
```

---

# Telegram API modes

Если:

```env
TELEGRAM_BOT_API_URL=
```

используется официальный `https://api.telegram.org`.

Если указан self-hosted endpoint:

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
```

используется `bots.tgapi`.

`TELEGRAM_BOT_API_LOCAL=true` нужен только если сам `telegram-bot-api` запущен с `--local`.

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

---

# Обновление

```bash
cd anime-db-bot
git pull
./start.sh
```

Если уже запущена tmux-сессия:

```text
Restart the bot? [y/N]:
```

ответить:

```text
y
```

---

# tmux и логи

Подключиться:

```bash
tmux attach -t anime-db-bot
```

Логи:

```bash
tail -f logs/bot.log
```

Последние строки:

```bash
tail -n 100 logs/bot.log
```

---

# `start.sh`

Скрипт проверяет:

- Python;
- tmux;
- venv/pip;
- зависимости;
- импорты core/search/services/sources/bots;
- search registry;
- metadata registry;
- `.env`;
- `BOT_TOKEN`;
- режим Telegram API.

Пустой `MAL_CLIENT_ID` является предупреждением, а не фатальной ошибкой.

---

# Будущий локальный индекс

Позже планируется локальная база соответствий и названий.

Она должна находиться в search-слое и решать задачи:

```text
название → MAL ID
MAL ID ↔ AniList ID
MAL ID ↔ Shikimori ID
MAL ID ↔ AniDB ID
...
```

Это позволит:

- снизить число внешних поисковых запросов;
- улучшить поиск по альтернативным/русским названиям;
- получать cross-ID даже если пользователь выбрал только один внешний поисковик.

Metadata sources и AnimeAggregator при этом менять не потребуется.

---

# Главный принцип проекта

```text
Search providers находят сущность.
Metadata sources знают только свой API.
Core models описывают смысл данных, а не конкретную базу.
AnimeAggregator объединяет одинаковые поля без повторений.
Telegram показывает одну итоговую карточку.
```
