# anime-db-bot

Telegram-бот для поиска аниме и объединения метаданных из нескольких внешних баз данных в одну интерактивную карточку.

Главная идея проекта: **поиск и источники метаданных — это разные слои**.

Пользователь ищет аниме только через MyAnimeList. После выбора конкретного результата бот получает его **MAL ID** и передаёт этот ID источникам метаданных — сейчас Shikimori и AniList. Источники больше не выполняют текстовый поиск.

---

## Возможности

- `/anime <название>` — поиск через официальный MyAnimeList API v2;
- постраничная выдача без искусственного лимита «первые 5 результатов»;
- после выбора одного результата используется его MAL ID;
- параллельный запрос Shikimori и AniList только после выбора;
- объединение ответов источников в одну `AggregatedAnime`;
- отдельные оценки разных баз;
- объединение названий, жанров, студий, описаний, персонала, сэйю и постеров;
- rich messages Telegram;
- постер внутри той же карточки;
- кликабельные текстовые разделы `Описание`, `Все названия`, `Авторы и команда`, `Сэйю`;
- inline-кнопки только для `← Назад` и `◀️ / ▶️`;
- официальный Telegram Bot API и self-hosted `telegram-bot-api`;
- fallback на обычные сообщения, если rich message недоступен.

---

# Архитектура

```text
anime-db-bot/
├── core/
│   ├── __init__.py
│   ├── contracts.py
│   └── models.py
│
├── search/
│   ├── __init__.py
│   ├── mal.py
│   └── registry.py
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

Архитектура делится на пять независимых частей.

---

# 1. `core/` — общие модели и контракты

`core/` не знает ничего о Telegram, MyAnimeList, AniList или Shikimori.

## `core/models.py`

Основные модели:

### `SearchCandidate`

Один результат поисковика.

Для текущей архитектуры важнейшее поле:

```python
external_ids = {
    "mal": "37430",
}
```

То есть именно MAL ID становится универсальным идентификатором между поиском и источниками.

### `SearchPage`

Страница результатов поиска:

```python
SearchPage(
    items=[...],
    page=1,
    page_size=10,
    has_next=True,
)
```

### `AnimeRecord`

Нормализованный ответ **одного** источника метаданных.

Например `sources/anilist.py` преобразует GraphQL AniList в `AnimeRecord`, а `sources/shikimori.py` — GraphQL Shikimori в тот же формат.

### `AggregatedAnime`

Итоговая карточка после объединения всех доступных `AnimeRecord`.

---

## `core/contracts.py`

Здесь два разных контракта.

### `AnimeSearchProvider`

Отвечает только за поиск:

```python
async def search(
    query: str,
    *,
    page: int,
    limit: int,
) -> SearchPage:
    ...
```

### `AnimeSource`

Источник метаданных больше **не имеет `search()`**.

Его единственная основная обязанность:

```python
async def get_details(mal_id: str) -> AnimeRecord | None:
    ...
```

Это ключевой принцип текущей архитектуры.

---

# 2. `search/` — отдельный поисковик

Текстовый поиск вынесен полностью из `sources/`.

Сейчас единственный search provider:

```text
search/mal.py
```

Он использует официальный MyAnimeList API v2.

Схема:

```text
/anime slime
      │
      ▼
SearchService
      │
      ▼
MALSearchProvider
      │
      ▼
MyAnimeList API
      │
      ▼
SearchCandidate[]
```

Ни AniList, ни Shikimori на этом этапе вообще не вызываются.

## Почему MAL используется как поисковик

MAL ID поддерживается многими аниме-базами и удобен как внешний ключ.

Вместо ситуации:

```text
запрос пользователя
 ├─ Shikimori search
 ├─ AniList search
 ├─ AniDB search
 └─ ещё N поисков
```

теперь:

```text
запрос пользователя
       │
       ▼
      MAL
       │
       ▼
 выбран MAL ID
       │
       ├─ Shikimori.get_details(mal_id)
       ├─ AniList.get_details(mal_id)
       └─ будущие источники
```

Это существенно уменьшает число API-запросов и упрощает отладку.

---

# 3. `services/` — бизнес-логика

## `services/search.py`

`SearchService` знает только интерфейс `AnimeSearchProvider`.

Он не импортирует Shikimori/AniList и ничего не знает об их API.

Сейчас через `search/registry.py` ему передаётся `MALSearchProvider`.

## `services/aggregator.py`

После выбора результата поисковика агрегатор читает:

```python
mal_id = candidate.external_ids["mal"]
```

и параллельно вызывает:

```python
source.get_details(mal_id)
```

для всех зарегистрированных источников.

Если один источник не отвечает, другие продолжают работать.

Итог — одна `AggregatedAnime`.

---

# 4. `sources/` — только базы метаданных

Источники больше не отвечают за текстовый поиск.

Сейчас подключены:

```text
sources/shikimori.py
sources/anilist.py
```

## Shikimori

Получает MAL ID.

Бот пробует получить связанную Shikimori-запись и обязательно сверяет возвращённый `malId`.

Если ID не совпал, Shikimori просто возвращает `None`.

**Текстового fallback-поиска по названию нет.**

Это сделано намеренно: выбранный MAL ID должен оставаться единственным идентификатором запроса.

## AniList

AniList получает тот же MAL ID и делает GraphQL lookup через:

```graphql
Media(idMal: $idMal, type: ANIME)
```

Поэтому `/anime` больше не расходует лимит AniList.

AniList вызывается только после выбора конкретного результата.

Дополнительно могут запрашиваться страницы staff и characters/voice actors. Их число ограничивается `ANILIST_PEOPLE_MAX_PAGES`.

---

# 5. `bots/` — Telegram-интерфейс

Telegram-код не выполняет поиск в источниках напрямую.

Он знает только:

```text
SearchService
AnimeAggregator
```

Поток команды:

```text
/anime <query>
      │
      ▼
SearchService
      │
      ▼
MyAnimeList
      │
      ▼
пользователь выбирает результат
      │
      ▼
MAL ID
      │
      ▼
AnimeAggregator
      │
      ├─ Shikimori
      └─ AniList
      │
      ▼
AggregatedAnime
      │
      ▼
Telegram rich message
```

---

# Получение MyAnimeList Client ID

Для публичного MyAnimeList API v2 нужен **Client ID**.

OAuth access token для обычного публичного поиска не требуется.

## Шаг 1

Войди в свой аккаунт MyAnimeList.

Открой:

```text
https://myanimelist.net/apiconfig
```

## Шаг 2

Создай новое API-приложение.

Название можно использовать, например:

```text
anime-db-bot
```

Для текущего проекта нам нужен только Client ID для публичных запросов.

Если форма требует Redirect URL, можно указать локальный URL, например:

```text
http://localhost
```

Мы не используем OAuth flow, поэтому callback сейчас фактически не будет использоваться.

## Шаг 3

После создания приложения MyAnimeList покажет Client ID.

Скопируй его.

## Шаг 4

Открой `.env`:

```bash
nano .env
```

и добавь:

```env
MAL_CLIENT_ID=твой_client_id
```

Например структура конфига:

```env
BOT_TOKEN=...

MAL_CLIENT_ID=...
MAL_API_URL=https://api.myanimelist.net/v2

SHIKIMORI_API_URL=https://shikimori.io/api/graphql
SHIKIMORI_SITE_URL=https://shikimori.io

ANILIST_API_URL=https://graphql.anilist.co
ANILIST_ACCESS_TOKEN=
ANILIST_PEOPLE_MAX_PAGES=4
```

Client Secret сейчас боту не нужен.

Не публикуй Client Secret, если MAL всё же показывает его рядом с Client ID.

---

# MAL API search

Запрос выглядит примерно так:

```http
GET https://api.myanimelist.net/v2/anime?q=slime&limit=10&offset=0
X-MAL-CLIENT-ID: <MAL_CLIENT_ID>
```

Бот дополнительно просит несколько полей для более удобной выдачи:

```text
alternative_titles
start_date
mean
```

На странице Telegram показывается до 10 результатов.

Пагинация MAL преобразуется в:

```text
[ Anime 1 · MAL 123 ]
[ Anime 2 · MAL 456 ]
...

[ ◀️ ] [ Стр. 2 ] [ ▶️ ]
```

У бота нет общего лимита на число страниц.

## Важное ограничение поиска

Поиск выполняет именно MyAnimeList.

Поэтому качество совпадений зависит от названий, известных MAL. Запросы на английском, romaji или японском обычно наиболее предсказуемы.

Русское название может не находиться, если такого варианта названия нет в MAL. В таком случае попробуй английское или romaji-название.

---

# AniList и API key

Для текущего чтения публичных данных AniList отдельный API key не нужен.

Используется:

```env
ANILIST_API_URL=https://graphql.anilist.co
ANILIST_ACCESS_TOKEN=
```

`ANILIST_ACCESS_TOKEN` можно оставить пустым.

OAuth понадобится только если в будущем бот будет работать с пользовательским AniList-аккаунтом — например менять anime list, прогресс или оценку.

Главное изменение текущей архитектуры: **AniList больше не используется для поиска вообще**.

---

# Карточка аниме

Основная информация разбивается на логические блоки.

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

Производство:
Жанры: Фэнтези, Приключения
Студии: 8bit

Оценки:
MyAnimeList: 8.14
Shikimori: 8.31
AniList: 8.2

Источники:
Базы данных: Shikimori, AniList
ID: MAL: 37430 | SHIKIMORI: ... | ANILIST: ...
```

MAL может присутствовать в блоке оценок, потому что поисковая выдача MAL уже содержит `mean`. При этом MAL не считается metadata source: полный MAL detail endpoint агрегатор не запрашивает.

---

# Rich messages

Основная карточка использует `sendRichMessage`.

Постер находится внутри того же сообщения.

Разделы:

```text
Описание
Все названия
Авторы и команда
Сэйю
```

реализованы как кликабельные rich text buttons.

После нажатия редактируется то же сообщение.

Навигационные действия остаются обычными inline-кнопками:

```text
[ ← Назад ]
```

или:

```text
[ ← Назад ]
[ ◀️ ] [ 1/2 ] [ ▶️ ]
```

---

# Постеры

`AggregatedAnime.posters` содержит постеры от доступных metadata sources.

Shikimori выбирает лучший размер своего основного постера.

AniList выбирает:

```text
extraLarge
↓
large
↓
medium
```

Если источники возвращают разные постеры, Telegram может показать их как slideshow внутри rich message.

---

# Установка

На Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip tmux git
```

Клонирование:

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Конфиг:

```bash
cp .env.example .env
nano .env
```

Минимально обязательные значения:

```env
BOT_TOKEN=...
MAL_CLIENT_ID=...
```

Запуск:

```bash
./start.sh
```

---

# `start.sh`

Скрипт проверяет:

1. `python3`;
2. `tmux`;
3. структуру `core/`, `search/`, `services/`, `sources/`, `bots/`;
4. `.venv`;
5. `pip`;
6. зависимости;
7. импорты;
8. search provider registry;
9. metadata source registry;
10. `BOT_TOKEN`;
11. `MAL_CLIENT_ID`;
12. Telegram transport.

Без `MAL_CLIENT_ID` запуск намеренно остановится с понятной ошибкой, потому что основной `/anime` поиск без него не работает.

Если бот уже запущен:

```text
Restart the bot? [y/N]:
```

`y`, `yes`, `д`, `да` — перезапустить.

---

# Telegram API режимы

Официальный API:

```env
TELEGRAM_BOT_API_URL=
```

Self-hosted:

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=true
```

Логика бота одинакова в обоих режимах.

---

# tmux и логи

Подключение:

```bash
tmux attach -t anime-db-bot
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

# Добавление нового metadata source

Новый источник не должен реализовывать поиск.

Например:

```text
sources/anidb.py
```

Интерфейс:

```python
class AniDBSource:
    name = "AniDB"

    async def get_details(self, mal_id: str):
        ...
```

Если AniDB использует собственный ID, адаптер сам отвечает за преобразование MAL ID в свой ID.

После этого источник добавляется в:

```text
sources/registry.py
```

`search/mal.py`, `services/search.py` и Telegram-код менять не нужно.

---

# Замена поисковика

Если когда-нибудь вместо MAL понадобится другой search provider, создаётся, например:

```text
search/custom.py
```

реализующий `AnimeSearchProvider`, и меняется только:

```text
search/registry.py
```

Metadata sources при этом остаются неизменными.

---

# Текущая схема запросов

До выбора результата:

```text
Telegram
   │
   ▼
MyAnimeList
```

После выбора:

```text
MAL ID
  │
  ├──► Shikimori
  │
  └──► AniList
         │
         ▼
    AnimeAggregator
         │
         ▼
   Telegram card
```

AniList и Shikimori больше не получают исходный текст пользователя.

---

# Главный принцип

```text
MyAnimeList отвечает только за поиск.

Источники получают только выбранный MAL ID.

SearchService не знает metadata sources.

AnimeAggregator не знает, как выполнялся поиск.

Telegram получает только SearchPage и AggregatedAnime.
```

Это делает лимиты, ошибки и отладку каждого слоя независимыми друг от друга.
