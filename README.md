# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких баз данных.

Главный принцип проекта: **поиск, metadata sources, агрегирование и Telegram UI — отдельные слои**. Канонический ID между слоями сейчас — MAL ID.

## Что подключено

### Поиск

Обычный `/anime` использует параллельно:

- Shikimori Search;
- MyAnimeList Search.

Результаты объединяются строго по MAL ID. `/search` позволяет явно выбрать MAL, Shikimori, AniList, несколько источников или все сразу.

Если у выбранного результата нет Shikimori ID, `AnimeAggregator` вызывает `services/id_resolver.py`. Resolver выполняет отдельный Shikimori search и принимает запись только при **точном совпадении MAL ID**. Поэтому cross-ID восстановление одинаково работает для единственного результата `/anime`, MAL-only и AniList-only поиска, а metadata source сам не выполняет скрытый текстовый поиск.

### Метаданные

После выбора аниме используются:

- Shikimori;
- AniList;
- MyAnimeList.

`AnimeAggregator` объединяет семантически одинаковые данные: названия, жанры, студии, даты, статусы, оценки, персонал и другие поля. Источник сохраняется там, где provenance действительно нужен: внешние ID/URL, описания, варианты названий, staff/voices и портреты.

## Ленивая загрузка персонала

Главная карточка теперь **metadata-only** и не ждёт тяжёлые списки людей ни от Shikimori, ни от AniList.

- Shikimori staff загружается при первом открытии `Авторы и команда`.
- AniList staff загружается при первом открытии `Авторы и команда`.
- AniList Japanese voice actors загружаются при первом открытии `Сэйю`.
- Shikimori character-backed seiyuu (`anime roles -> character -> seyu`) загружаются при первом открытии `Сэйю`.
- Источники одного раздела загружаются параллельно.
- Данные вливаются в уже существующую `AggregatedAnime`; основная metadata карточки повторно не запрашивается.
- Повторные открытия используют данные карточки и RAM-кеши источников.

Для Shikimori REST есть общий для процесса rate limiter и до трёх попыток после HTTP 429 с учётом `Retry-After`. Это защищает тяжёлую character→seyu цепочку при одновременных запросах нескольких пользователей.

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
│   ├── common.py
│   ├── official.py
│   ├── people_portraits.py
│   ├── runner.py
│   ├── search_ui.py
│   ├── session_store.py
│   └── tgapi.py
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
│   ├── shikimori.py
│   └── shikimori_people.py
├── tests/
│   ├── test_aggregator.py
│   ├── test_anilist_lazy.py
│   ├── test_search.py
│   ├── test_session_store.py
│   └── test_shikimori_people.py
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements.lock
├── start.sh
└── README.md
```

## Поток данных

```text
/anime или /search
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

People callbacks подключены через явный aiogram middleware в `bots/runner.py`; runtime monkeypatch функций `bots.common` не используется.

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

Search и anime-card sessions используют ограниченное in-memory хранилище со sliding TTL: активная карточка продлевается при использовании, заброшенный callback token удаляется после периода бездействия. Служебное lazy-people состояние ограничено тем же TTL-подходом. После перезапуска процесса RAM-кеши очищаются.

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
- cross-ID enrichment до запуска metadata sources;
- идентичность персонала по source IDs;
- фильтрацию localization staff;
- source-keyed portrait merge;
- Shikimori `character -> seyu` parsing;
- отсутствие `personRoles` Shikimori и people pagination AniList в initial metadata path;
- callback session TTL и ограничение размера session store.

`start.sh` перед запуском процесса выполняет те же unit tests, compile check, `pip check` и быстрый wiring smoke test.

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

При обычном обновлении сервера достаточно:

```bash
git pull
./start.sh
```

`start.sh` проверяет файлы, создаёт/проверяет `.venv`, устанавливает `requirements.lock`, запускает тесты и smoke checks, затем запускает бота в `tmux`. Runtime-лог пишется в `logs/bot.log`; `logs/` исключён из Git.
