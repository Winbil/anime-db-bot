# anime-db-bot

Telegram-бот для поиска аниме и объединения информации из нескольких внешних баз данных в одну карточку.

Сейчас подключены два источника:

- **Shikimori**;
- **AniList**.

Архитектура построена так, чтобы поиск, агрегация и Telegram-интерфейс не зависели от конкретной базы данных.

## Что умеет бот

- `/start` — показывает режим Telegram API и подключённые источники;
- `/ping` — проверяет, что бот работает;
- `/anime <название>` — ищет аниме одновременно во всех подключённых источниках;
- объединяет одинаковые результаты разных источников в один вариант;
- после выбора запрашивает подробности у всех доступных источников;
- объединяет названия, оценки, жанры, студии, описания, персонал, сэйю, постеры, ссылки и внешние ID;
- показывает результат как интерактивную rich-карточку Telegram;
- позволяет открывать `Описание`, `Все названия`, `Авторы и команда` и `Сэйю` нажатием на текст внутри сообщения;
- оставляет обычные inline-кнопки для `← Назад` и перелистывания `◀️ / ▶️`;
- поддерживает официальный `api.telegram.org` и свой `telegram-bot-api`.

---

# Архитектура

```text
anime-db-bot/
├── core/
│   ├── __init__.py
│   ├── contracts.py
│   └── models.py
│
├── services/
│   ├── __init__.py
│   ├── search.py
│   └── aggregator.py
│
├── sources/
│   ├── __init__.py
│   ├── registry.py
│   ├── shikimori.py
│   └── anilist.py
│
├── bots/
│   ├── __init__.py
│   ├── common.py
│   ├── official.py
│   └── tgapi.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── start.sh
└── README.md
```

Проект разделён на четыре основных слоя.

## `core/`

Общие контракты и модели, которые не зависят ни от Telegram, ни от конкретной базы данных.

### `core/models.py`

Содержит универсальные структуры:

- `SourceSearchHit` — результат поиска одного источника;
- `SourceSearchPage` — страница результатов конкретного источника;
- `SearchCandidate` — объединённый поисковый результат;
- `SearchPage` — страница универсального поисковика;
- `PersonCredit` — человек и его роли;
- `AnimeRecord` — нормализованный ответ одного источника;
- `AggregatedAnime` — итоговая карточка после объединения всех источников.

### `core/contracts.py`

Содержит контракт `AnimeSource`.

Каждый источник должен реализовать только:

```python
async def search(query, page, limit) -> SourceSearchPage
async def get_details(candidate) -> AnimeRecord | None
```

`SearchService` и `AnimeAggregator` работают только через этот контракт.

---

# Поисковый сервис

Файл:

```text
services/search.py
```

`SearchService` получает список адаптеров и выполняет поиск по ним параллельно.

```text
/anime slime
      │
      ▼
SearchService
      │
      ├── Shikimori.search(...)
      ├── AniList.search(...)
      └── будущие источники
      │
      ▼
объединение результатов
      │
      ▼
SearchCandidate[]
```

`services/search.py` не импортирует конкретные источники и ничего не знает о GraphQL Shikimori или AniList.

## Как склеиваются одинаковые результаты

В первую очередь используется общий **MyAnimeList ID**.

Например:

```text
Shikimori:
MAL: 37430

AniList:
MAL: 37430
```

Оба результата становятся одним `SearchCandidate`.

Если общего MAL ID нет, используется нормализованная комбинация:

```text
название + год
```

## Ошибка одного источника

Ошибка одной базы не должна ломать весь поиск.

Если AniList временно недоступен, Shikimori продолжит работать, и наоборот.

---

# Агрегатор

Файл:

```text
services/aggregator.py
```

После выбора результата `AnimeAggregator` запрашивает подробности у всех источников.

```text
SearchCandidate
      │
      ▼
AnimeAggregator
      │
      ├── Shikimori.get_details(candidate)
      ├── AniList.get_details(candidate)
      └── ...
      │
      ▼
AnimeRecord[]
      │
      ▼
AggregatedAnime
      │
      ▼
Telegram rich message
```

Агрегатор объединяет:

- названия;
- синонимы;
- внешние ID;
- тип;
- статус;
- возрастной рейтинг;
- количество и прогресс серий;
- длительность;
- даты показа;
- оценки каждого источника;
- жанры;
- студии;
- лицензиатов;
- описания;
- постеры;
- ссылки;
- авторов и команду;
- сэйю.

Оценки разных сайтов хранятся отдельно. AniList `averageScore` преобразуется из шкалы 0–100 в шкалу 0–10, поэтому карточка может выглядеть так:

```text
Оценки:
Shikimori: 8.31
AniList: 8.2
```

---

# Источники

Конкретные базы находятся только в:

```text
sources/
```

Сейчас доступны:

```text
sources/shikimori.py
sources/anilist.py
```

Telegram-логика внутри адаптеров отсутствует.

## Shikimori

`sources/shikimori.py` отвечает только за:

- Shikimori GraphQL;
- поиск;
- получение подробной записи;
- статусы и типы Shikimori;
- постер;
- персонал и роли;
- нормализацию в `SourceSearchHit` и `AnimeRecord`.

## AniList

`sources/anilist.py` использует публичный GraphQL endpoint:

```text
https://graphql.anilist.co
```

Он добавляет:

- AniList ID;
- MAL ID;
- romaji / English / native названия;
- синонимы;
- формат и статус;
- сезон и год;
- количество серий;
- длительность;
- даты выхода;
- `averageScore`;
- жанры;
- студии;
- описание;
- cover image;
- следующую выходящую серию;
- staff;
- voice actors;
- ссылку на страницу AniList.

Для staff и персонажей AniList использует пагинацию по 25 записей. Количество запрашиваемых страниц ограничивается `ANILIST_PEOPLE_MAX_PAGES`, чтобы один просмотр карточки не создавал слишком много API-запросов.

---

# Нужен ли AniList API key?

Для текущего бота — **нет**.

Публичные данные AniList доступны без OAuth, client ID, client secret и access token.

Без авторизации можно получать публичные anime/manga данные и выполнять обычный поиск.

OAuth нужен, если позже появятся функции вроде:

- авторизации пользователя AniList;
- чтения приватного профиля текущего пользователя;
- работы с user-specific полями;
- изменения anime/manga списка;
- других mutations.

В `.env` предусмотрено необязательное поле:

```env
ANILIST_ACCESS_TOKEN=
```

Оставляй его пустым для обычного поиска и метаданных.

## Если OAuth всё-таки понадобится

1. Войти в AniList.
2. Открыть настройки разработчика:

```text
https://anilist.co/settings/developer
```

3. Нажать `Create New Application`.
4. Указать название приложения.
5. Указать Redirect URL.
6. AniList выдаст `Client ID` и `Client Secret`.

Для серверного приложения подходит **Authorization Code Grant**.

Если нужен простой ручной токен без собственного callback-сервера, можно установить Redirect URL:

```text
https://anilist.co/api/v2/oauth/pin
```

AniList access token действует около года; refresh token в текущем OAuth не используется.

Важно: `Client Secret` и access token нельзя коммитить в GitHub.

---

# Реестр источников

Файл:

```text
sources/registry.py
```

Сейчас в нём подключены:

```python
return (
    ShikimoriSource(),
    AniListSource(),
)
```

Чтобы отключить источник, достаточно убрать его из registry.

Поиск и агрегатор при этом менять не требуется.

---

# Как добавить новый источник

Создать отдельный файл, например:

```text
sources/anidb.py
```

Адаптер должен реализовать общий контракт:

```python
class AniDBSource:
    name = "AniDB"

    async def search(self, query, *, page, limit):
        ...

    async def get_details(self, candidate):
        ...
```

`search()` возвращает `SourceSearchPage`, содержащий `SourceSearchHit`.

`get_details()` возвращает `AnimeRecord`.

После этого адаптер добавляется в:

```text
sources/registry.py
```

`services/search.py`, `services/aggregator.py` и Telegram-слой не должны содержать специальных веток для нового API.

---

# Telegram-слой

Файлы:

```text
bots/common.py
bots/official.py
bots/tgapi.py
```

`bots/common.py` отвечает за:

- команды;
- callback handlers;
- временные поисковые сессии;
- временные `AggregatedAnime`;
- форматирование итоговой модели;
- rich messages;
- пагинацию;
- fallback на обычные сообщения.

Он не работает с исходными GraphQL-полями Shikimori или AniList.

## Основная карточка

Информация теперь разделена на логические блоки:

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
Лицензиаты: ...

Оценки:
Shikimori: 8.31
AniList: 8.2

Источники:
Базы: Shikimori, AniList
ID: MAL: ... | SHIKIMORI: ... | ANILIST: ...
Shikimori: https://...
AniList: https://...
```

---

# Rich messages

Основная карточка использует `sendRichMessage`.

В неё могут входить:

- постеры;
- текст;
- callback-ссылки прямо внутри текста.

Разделы:

```text
Описание — нажмите, чтобы открыть
Все названия — нажмите, чтобы открыть
Авторы и команда — нажмите, чтобы открыть
Сэйю — нажмите, чтобы открыть
```

После нажатия бот редактирует то же сообщение.

В открытом разделе используются обычные inline-кнопки:

```text
[ ← Назад ]
```

При необходимости:

```text
[ ← Назад ]
[ ◀️ ] [ 1/2 ] [ ▶️ ]
```

---

# Постеры

Постеры разных источников объединяются в:

```python
AggregatedAnime.posters
```

Shikimori выбирает лучший размер своего основного постера.

AniList использует приоритет:

```text
extraLarge
↓
large
↓
medium
```

Если Shikimori и AniList вернут разные изображения, rich-карточка может показать их как slideshow.

---

# Поиск и пагинация

У бота нет общего ограничения вида «только первые 5 результатов».

Каждый источник получает:

```python
query
page
limit
```

Telegram показывает результаты постранично.

Сейчас размер страницы интерфейса:

```text
10 результатов
```

```text
[ Anime 1 ]
...
[ Anime 10 ]

[ ◀️ ] [ Стр. 2 ] [ ▶️ ]
```

Shikimori и AniList оба поддерживают свою пагинацию, а `SearchService` объединяет их выдачу.

---

# Временные сессии

Состояние пока хранится в RAM процесса:

- поисковые сессии;
- агрегированные карточки для callback-навигации.

После перезапуска старые callback'и могут устареть.

Позже этот слой можно вынести в Redis, SQLite или PostgreSQL, не меняя источники.

---

# Установка

Требуется:

- Python 3.11+;
- `python3-venv`;
- `tmux`;
- Git;
- Telegram bot token.

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip tmux git
```

Клонирование:

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Создать `.env`:

```bash
cp .env.example .env
nano .env
```

Минимально нужно только:

```env
BOT_TOKEN=123456:your_bot_token
```

AniList для публичных данных заработает без дополнительной регистрации.

Запуск:

```bash
./start.sh
```

---

# `.env`

Пример:

```env
BOT_TOKEN=

TELEGRAM_BOT_API_URL=
TELEGRAM_BOT_API_LOCAL=false

SHIKIMORI_API_URL=https://shikimori.io/api/graphql
SHIKIMORI_SITE_URL=https://shikimori.io

ANILIST_API_URL=https://graphql.anilist.co
ANILIST_ACCESS_TOKEN=
ANILIST_PEOPLE_MAX_PAGES=4
```

## AniList переменные

### `ANILIST_API_URL`

URL публичного GraphQL API.

Обычно менять не нужно:

```env
ANILIST_API_URL=https://graphql.anilist.co
```

### `ANILIST_ACCESS_TOKEN`

Необязательный OAuth bearer token.

Для текущих публичных данных должен оставаться пустым:

```env
ANILIST_ACCESS_TOKEN=
```

### `ANILIST_PEOPLE_MAX_PAGES`

Ограничивает количество страниц staff/characters, которое адаптер может забрать для одной карточки.

AniList выдаёт максимум 25 таких элементов на страницу.

По умолчанию:

```env
ANILIST_PEOPLE_MAX_PAGES=4
```

То есть максимум примерно 100 элементов каждого типа до дедупликации.

---

# Telegram API режимы

## Официальный Telegram Bot API

```env
TELEGRAM_BOT_API_URL=
```

Запускается:

```text
bots.official
```

## Self-hosted Telegram Bot API

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=true
```

Запускается:

```text
bots.tgapi
```

`TELEGRAM_BOT_API_LOCAL=true` нужен только если сервер `telegram-bot-api` запущен с `--local`.

---

# `start.sh`

Скрипт:

1. проверяет `python3`;
2. проверяет `tmux`;
3. проверяет структуру файлов;
4. создаёт `.venv`;
5. восстанавливает `pip`, если требуется;
6. устанавливает зависимости;
7. выполняет `pip check`;
8. проверяет imports и registry источников;
9. проверяет `.env` и `BOT_TOKEN`;
10. выбирает Telegram transport;
11. запускает бот в tmux.

При повторном запуске:

```text
Bot is already running in tmux session 'anime-db-bot'.
Restart the bot? [y/N]:
```

`y`, `yes`, `д`, `да` — перезапустить.

Любой другой ответ — оставить текущий экземпляр.

---

# tmux и логи

Подключиться:

```bash
tmux attach -t anime-db-bot
```

Отсоединиться, не останавливая процесс:

```text
Ctrl+B
D
```

Логи:

```bash
tail -f logs/bot.log
```

Последние 100 строк:

```bash
tail -n 100 logs/bot.log
```

---

# Обновление

```bash
cd anime-db-bot
git pull
./start.sh
```

Если бот работает — ответить `y` на предложение перезапуска.

---

# Основные зависимости

- `aiogram` — Telegram Bot API;
- `httpx` — HTTP/GraphQL запросы;
- `python-dotenv` — `.env`.

---

# Планируемые источники

- AniDB — более глубокая техническая метаинформация;
- AnimeThemes — OP/ED, исполнители и видео;
- SkipDB — opening / recap / ending / preview тайминги;
- другие базы по необходимости.

---

# Главный принцип проекта

```text
Источник знает только свой API.
Поиск знает только общий контракт.
Агрегатор знает только нормализованные модели.
Telegram знает только итоговую AggregatedAnime.
```

Это позволяет добавлять, отключать или переписывать отдельные базы без переделки всего бота.
