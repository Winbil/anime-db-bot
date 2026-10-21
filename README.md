# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких баз данных.

Главный принцип проекта: **поиск, metadata sources, агрегирование и UI конкретной платформы — отдельные слои**. Канонический ID между слоями сейчас — MAL ID.

## Что подключено

### Поиск

Обычный `/anime` использует параллельно:

- Shikimori Search;
- MyAnimeList Search.

Результаты объединяются строго по MAL ID. `/search` позволяет явно выбрать MAL, Shikimori, AniList, несколько источников или все сразу.

`/anime` и `/search` теперь используют один `SearchSession`, одну пагинацию и один набор callback namespaces (`xs/xp/xk`). Разница только в UX: `/anime` сразу запускает основной набор поисковиков, а `/search` без указанного scope сначала предлагает выбрать источники.

Если у выбранного результата нет Shikimori ID, `AnimeAggregator` вызывает `services/id_resolver.py`. Resolver выполняет отдельный Shikimori search и принимает запись только при **точном совпадении MAL ID**. Поэтому cross-ID восстановление одинаково работает для единственного результата `/anime`, MAL-only и AniList-only поиска, а metadata source сам не выполняет скрытый текстовый поиск.

### Метаданные

После выбора аниме используются:

- Shikimori;
- AniList;
- MyAnimeList.

`AnimeAggregator` объединяет семантически одинаковые данные: названия, жанры, студии, даты, статусы, оценки, персонал и другие поля. Источник сохраняется там, где provenance действительно нужен: внешние ID/URL, описания, варианты названий, staff/voices и портреты.

## Ленивая загрузка персонала

Главная карточка **metadata-only** и не ждёт тяжёлые списки людей ни от Shikimori, ни от AniList.

- Shikimori staff загружается при первом открытии `Авторы и команда`.
- AniList staff загружается при первом открытии `Авторы и команда`.
- AniList Japanese voice actors загружаются при первом открытии `Сэйю`.
- Shikimori character-backed seiyuu (`anime roles -> character -> seyu`) загружаются при первом открытии `Сэйю`.
- Источники одного раздела загружаются параллельно.
- Данные вливаются в уже существующую `AggregatedAnime`; основная metadata карточки повторно не запрашивается.
- Повторные открытия используют данные карточки и RAM-кеши источников там, где они предусмотрены adapter-слоем.

Для Shikimori REST есть общий для процесса rate limiter и до трёх попыток после HTTP 429 с учётом `Retry-After`. Это защищает тяжёлую character→seyu цепочку при одновременных запросах нескольких пользователей.

Retry-обёртка `sources/resilient.py` больше не реализует собственную Shikimori business logic: она только повторяет временно упавшие операции и сохраняет реальные capabilities исходного adapter-а.

## Команды

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

## Архитектура

```text
anime-db-bot/
├── .github/workflows/ci.yml
├── bots/
│   ├── __init__.py
│   ├── session_store.py
│   └── telegram/
│       ├── __init__.py
│       ├── bot.py
│       ├── card_handlers.py
│       ├── common.py
│       ├── people_portraits.py
│       ├── search_ui.py
│       └── transports/
│           ├── __init__.py
│           ├── official.py
│           └── tgapi.py
├── core/
│   ├── canonicalization.py
│   ├── contracts.py
│   ├── http_config.py
│   └── models.py
├── search/
│   ├── registry.py
│   └── providers/
│       ├── anilist.py
│       ├── mal.py
│       └── shikimori.py
├── services/
│   ├── aggregator.py
│   ├── id_resolver.py
│   └── search.py
├── sources/
│   ├── anilist.py
│   ├── mal.py
│   ├── registry.py
│   ├── resilient.py
│   ├── shikimori.py
│   └── shikimori_people.py
├── tests/
│   ├── test_aggregator.py
│   ├── test_anilist_lazy.py
│   ├── test_resilient_sources.py
│   ├── test_search.py
│   ├── test_search_ui.py
│   ├── test_session_store.py
│   ├── test_shikimori_description.py
│   ├── test_shikimori_people.py
│   └── test_startup_wiring.py
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements.lock
├── start.sh
└── README.md
```

### Платформенный слой ботов

`bots/` больше не считается синонимом Telegram. Это контейнер для реализаций разных платформ.

- `bots/telegram/` — текущая Telegram-реализация.
- `bots/telegram/bot.py` — единственная точка сборки и запуска Telegram-бота.
- `bots/telegram/search_ui.py` — весь `/anime` + `/search` flow и search callback state.
- `bots/telegram/card_handlers.py` — `/start`, `/ping` и callback handlers обычных разделов карточки.
- `bots/telegram/common.py` — общие Telegram-сервисы, anime-card state, форматирование и рендеринг карточки.
- `bots/telegram/people_portraits.py` — lazy staff/seiyuu + rich portrait UI.
- `bots/telegram/transports/official.py` и `tgapi.py` — только transport-конфигурации для official Bot API и локального `tg-bot-api`.
- `bots/session_store.py` — общий platform-neutral helper для callback/session state.

Для следующей платформы можно добавить отдельный package, например `bots/discord/`, не смешивая Discord handlers/runtime с Telegram-кодом и не меняя `core/`, `search/`, `services/` и `sources/`.

`start.sh` всегда запускает один модуль `bots.telegram.bot`. Сам `bot.py` выбирает transport: official API по умолчанию или локальный `tg-bot-api`, если задан `TELEGRAM_BOT_API_URL`.

Старые верхнеуровневые `bots/runner.py`, `bots/official.py`, `bots/tgapi.py`, `bots/common.py`, `bots/search_ui.py`, `bots/card_handlers.py` и `bots/people_portraits.py` удалены.

## Поток данных

```text
/anime или /search
        │
        ▼
 bots/telegram/search_ui.py
        │
        ▼
 Search providers
        │
        ▼
SearchCandidate (MAL ID + известные cross-ID)
        │
        ├── при необходимости: MAL -> Shikimori ID resolver
        │
        ▼
 metadata-only sources
 Shikimori + AniList + MAL
        │
        ▼
 AnimeAggregator
        │
        ▼
 AggregatedAnime
        │
        ▼
 Telegram rich card
        │
        ├── Авторы и команда -> Shikimori + AniList lazy staff
        └── Сэйю             -> Shikimori + AniList lazy voices
```

People callbacks подключены через явный aiogram middleware в `bots/telegram/bot.py`; runtime monkeypatch функций `bots.telegram.common` не используется.

## SearchService

`services/search.py`:

1. нормализует запрос;
2. параллельно вызывает выбранные поисковики;
3. изолирует ошибку одного провайдера;
4. объединяет записи по MAL ID;
5. объединяет aliases, cross-ID и оценки;
6. для кириллического запроса предпочитает русское название Shikimori;
7. ограничивает объединённую страницу реальным `page_size`;
8. использует RAM LRU-кеш успешных страниц.

Частично сломанная страница с ошибкой одного провайдера **не кешируется**, поэтому временный сбой не остаётся в памяти на весь TTL.

```env
SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
```

## Metadata contracts

Search provider:

```python
async def search(query: str, *, page: int, limit: int) -> SearchPage: ...
```

Metadata source:

```python
async def get_details(
    mal_id: str,
    known_ids: dict[str, str],
) -> AnimeRecord | None: ...
```

Тяжёлые источники людей дополнительно могут предоставлять:

```python
async def load_staff(mal_id: str, known_ids: dict[str, str]) -> list[PersonCredit]: ...
async def load_voices(mal_id: str, known_ids: dict[str, str]) -> list[PersonCredit]: ...
```

Retry-proxy не добавляет эти capabilities metadata-only источникам: lazy people loader видит только операции, которые реально поддерживает исходный adapter.

## Персонал и портреты

`PersonCredit` хранит имя, aliases, роли, source-local external IDs и source-keyed portraits.

```python
{
    "AniList": ["..."],
    "Shikimori": ["..."],
}
```

Внешний ID используется как сильный сигнал идентичности. Если два одноимённых человека имеют конфликтующие ID одной базы, они не объединяются только по имени. Локализационные/dub credits удаляются из оригинального staff целиком. Для сэйю используются оригинальные японские связи источников.

В Telegram страница `0` показывает людей без портрета, затем идёт один человек на страницу. Несколько портретов выводятся rich slideshow; кнопка конкретного источника появляется только при наличии его портрета.

## RAM-кеши и callback-сессии

Shikimori:

```env
SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS=21600
SHIKIMORI_REST_MIN_INTERVAL_SECONDS=0.24
```

AniList:

```env
ANILIST_PEOPLE_MAX_PAGES=4
ANILIST_PEOPLE_CACHE_TTL_SECONDS=21600
```

Telegram callback state:

```env
TELEGRAM_SESSION_TTL_SECONDS=3600
```

Search и anime-card sessions используют ограниченное in-memory хранилище со sliding TTL и настоящим LRU-порядком: активная карточка продлевается и становится most-recently-used, заброшенный callback token удаляется после периода бездействия. Служебное lazy-people состояние ограничено тем же TTL-подходом. После перезапуска процесса RAM-кеши очищаются.

## Зависимости

`requirements.txt` содержит прямые runtime-зависимости проекта. `requirements.lock` содержит **полностью разрешённый набор прямых и транзитивных версий**, который устанавливают `start.sh` и CI. Поэтому обычный перезапуск сервера не должен неожиданно получить новую версию транзитивной библиотеки без коммита в репозиторий.

Все HTTP-адаптеры используют единый `USER_AGENT` и версию приложения из `core/http_config.py`.

## Тесты и CI

GitHub Actions запускает на Python 3.11, 3.12 и 3.13:

```bash
python -m compileall -q bots core search services sources tests
python -m unittest discover -s tests -v
```

Regression-тесты покрывают в том числе:

- ограничение объединённой поисковой страницы;
- кеширование успешных и повторный запрос ошибочных search pages;
- единый `/anime` + `/search` UI flow и отсутствие legacy search runtime в `common.py`;
- выбор official/local Telegram transport по конфигурации;
- импорт новой платформенной структуры `bots.telegram.*`;
- cross-ID enrichment до запуска metadata sources;
- идентичность персонала по source IDs;
- фильтрацию localization staff;
- source-keyed portrait merge;
- Shikimori `character -> seyu` parsing;
- отсутствие `personRoles` Shikimori и people pagination AniList в initial metadata path;
- source capability preservation в retry proxy;
- callback session TTL, LRU и ограничение размера session store;
- import/wiring smoke checks, которые раньше находились прямо внутри `start.sh`.

`start.sh` перед запуском процесса устанавливает lock-файл, выполняет `pip check`, compile check и тот же полный unit-test suite. Отдельного вручную поддерживаемого embedded smoke-script больше нет.

## Запуск

```bash
cp .env.example .env
nano .env
./start.sh
```

Минимально нужен:

```env
BOT_TOKEN=...
```

Для MAL Search/metadata нужен:

```env
MAL_CLIENT_ID=...
```

Если `TELEGRAM_BOT_API_URL` не задан, Telegram-бот использует официальный `api.telegram.org`. Если URL задан, `bots.telegram.bot` выбирает local `tg-bot-api` transport; `TELEGRAM_BOT_API_LOCAL` продолжает управлять режимом локального Bot API server.

При обычном обновлении сервера достаточно:

```bash
git pull
./start.sh
```

`start.sh` создаёт/проверяет `.venv`, устанавливает `requirements.lock`, запускает проверки и тесты, затем запускает `bots.telegram.bot` в `tmux`. Runtime-лог пишется в `logs/bot.log`; `logs/` исключён из Git.
