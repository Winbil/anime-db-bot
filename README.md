# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких независимых баз данных.

Главный принцип проекта: **search, identity, metadata sources, mappings, aggregation, localization и platform UI — отдельные слои**. Ни MAL, ни AniList, ни Shikimori, ни AniDB не считаются «главной» базой: `AnimeIdentity` хранит подтверждённые external IDs как равноправные связи.

## Поиск

Единственная пользовательская команда поиска — `/anime`. Старой `/search` нет и возвращать её не нужно.

Быстрый режим:

```text
/anime <название>
```

параллельно использует:

- Shikimori Search;
- MyAnimeList Search;
- AniList Search.

`/anime` без аргумента открывает пошаговый выбор `Все / MAL / Shikimori / AniList`. Pending input хранится только для конкретной пары user/chat, имеет TTL и отменяется `/cancel`.

Числовой запрос — source-independent direct lookup:

```text
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
```

Одинаковое число в разных базах **никогда** само по себе не означает одну сущность. Direct lookup не использует title-only merge: стартовый source должен подтвердить свой ID, а объединение происходит только по подтверждённым cross-ID edges.

Text search сначала объединяет результаты по непротиворечивым external IDs, затем может использовать точный нормализованный romaji fallback для ещё не связанных результатов. Конфликт ID одного provider всегда запрещает merge.

Перед Telegram-пагинацией `SearchService.collect()` формирует query-scoped relevant result set. Relevance policy учитывает title/romaji/native/aliases, prefix/token matches, transliteration и консервативный similarity fallback. Нерелевантный хвост upstream страниц останавливается, hard caps защищают quota. Telegram листает уже зафиксированный локальный набор, поэтому `▶` не делает новый upstream search.

Если итог не гарантирован из-за hard cap или частично недоступных sources, UI показывает честное `N/N+`, а не выдуманный точный count.

## Identity и mappings

```text
SearchCandidate
      │
      ▼
AnimeIdentity
├── mal: ...
├── anilist: ...
├── shikimori: ...
└── anidb: ...
```

`AnimeIdentity` не имеет primary ID. Каждый source использует только тот ключ, который умеет обслуживать.

Cross-ID enrichment построен консервативно:

1. direct accepted mappings из disk-backed SQLite;
2. live MAL → Shikimori fallback там, где он действительно нужен;
3. после расширения identity aggregator один раз повторяет ранее неприменимые sources.

Произвольного recursive graph traversal через TVDB/TMDB и другие промежуточные сущности в production нет. Такой traversal опасен для season/special grouping и был удалён.

Mappings DB строится потоково из нескольких datasets и остаётся на диске — полный граф не копируется в RAM. Directional manual overrides поддерживают `accept` и `reject`; overrides сохраняются при atomic rebuild.

## Metadata sources

Основные sources:

- Shikimori;
- AniList;
- MAL (MyAnimeList) / Jikan;
- AniDB — optional, включается только при настроенном `ANIDB_CLIENT`.

### MAL / Jikan

Jikan — **не отдельная identity-база**. Это локальный on-demand MAL web supplement. В `AnimeIdentity` нет `jikan` key; provenance хранится как `source=mal`, `backend=jikan`.

Jikan дополняет официальный MAL API тем, чего там не хватает для текущего UI: licensors, score distribution, lazy staff, Japanese voice actors, characters, trailers/promos и episodes. Ошибка локального Jikan parser не ломает официальный MAL metadata/search.

### AniDB

AniDB не участвует в обычном text search. Его ID появляется через mappings/direct lookup. HTTP source включается только при `ANIDB_CLIENT`.

AniDB сохраняет XML cache на диске, сериализует process-wide network requests и выдерживает минимальный интервал между обращениями. Из XML доступны metadata, staff, original voices, characters и episodes.

## Lazy sections

Главная карточка остаётся metadata-first. Тяжёлые разделы загружаются только при открытии:

- staff;
- original Japanese seiyuu;
- characters;
- trailers;
- episodes.

Foreign dub voices не входят в основной voice list. Localization/ADR staff отфильтровывается из original production staff.

`PersonCredit` и `CharacterRecord` — разные domain models. Portraits хранят provenance по source, а не одним плоским URL.

People UI разделён на:

```text
bots/telegram/people_loading.py   # progress/state и progressive batches
bots/telegram/people_views.py     # rendering/keyboards
bots/telegram/people_portraits.py # callback orchestration
```

Страница `0` существует только если действительно есть записи без портрета; иначе UI сразу начинает с portrait page.

## Source catalog и configuration

Source keys типизированы в `core/source_keys.py`, а capabilities объявлены в `core/capabilities.py`. Jikan намеренно отсутствует среди identity sources и остаётся backend’ом MAL.

Environment parsing централизован в `core/settings.py`:

```text
AppSettings
├── TelegramSettings
├── StorageSettings
├── SearchSettings
├── MappingSettings
├── SourceSettings
└── RateLimitSettings
```

Runtime-модули не должны самостоятельно разбирать `os.getenv()`; они получают typed settings через composition layer или совместимые typed accessors.

## AppContext и lifecycle

`services/app_context.py` — application composition root. Один `AppContext` владеет:

- `AppSettings`;
- shared `HttpClientPool`;
- `SourceHealthRegistry`;
- search providers;
- metadata sources;
- `SearchService`;
- `AnimeAggregator`;
- lazy character/episode/trailer services;
- direct lookup service.

Telegram runtime создаёт context при старте, активирует его на время dispatch и закрывает owned resources при shutdown. Импорт UI-модулей сам по себе не должен создавать runtime services.

## Shared HTTP, errors и source health

Outbound source HTTP проходит через общий transport boundary в `core/http_client.py`. Он переиспользует `httpx.AsyncClient` внутри application lifecycle и нормализует сетевые/HTTP ошибки в typed source errors из `core/source_errors.py`.

Resilience layer различает transient и non-transient failures. `SourceHealthRegistry` отслеживает последовательные transient failures и открывает circuit breaker после порога; успешный запрос сбрасывает failure state.

Provider-specific safety semantics сохраняются поверх общего transport: например, AniDB serialization/min interval и Shikimori people Retry-After handling.

## Rate limiting

Personal Telegram limits scoped по `(platform, user_id)`. Общего user bucket на всех пользователей нет.

Admin bypass относится только к personal limiter. Upstream provider safety limits остаются отдельными и обязательными даже для admin.

## Telegram callbacks

`bots/telegram/callbacks.py` содержит типизированный codec для существующих callback namespaces (`av`, `as`, `ad`, `ap`, `ae`, `ac`, `at`). Card handlers разбирают payload через codec, сохраняя прежний wire-format и совместимость уже отправленных кнопок.

Search/card callback sessions остаются bounded in-memory state со sliding TTL/LRU и привязкой к владельцу.

## Localization и settings

Поддерживаются:

- `ru`;
- `en`.

Domain model locale-neutral: source adapters сохраняют canonical status/kind/season/genre/role values, а перевод выполняется только в renderer/localization layer. Свободные descriptions машинно не переводятся.

Пользовательский locale и registry известных Telegram users хранятся в SQLite. Баны также persistent и platform-scoped.

## Команды

```text
/start
/ping
/settings
/anime
/anime <название>
/anime <external_id>
/anime mal:<id>
/anime anilist:<id>
/anime shikimori:<id>
/cancel

# admin-only
/users
/ban <user_id> [seconds] [reason]
/unban <user_id>
```

## Запуск

```bash
cd anime-db-bot
git pull
./start.sh
```

Обычный `start.sh` больше не переустанавливает dependencies и не запускает весь test suite при каждом restart.

Разделение задач:

```text
scripts/setup.sh           # создать/починить venv и поставить requirements.lock
scripts/check.sh           # compile + unit tests
scripts/update-mappings.sh # явное обновление mappings DB
start.sh                   # config/Jikan checks + запуск bot в tmux
```

`start.sh` остаётся executable (`100755`).

## Jikan container

Локальный parser-service находится в этом репозитории:

```text
compose.yml
jikan_service/
├── Dockerfile
├── composer.json
└── public/router.php
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Он слушает localhost и используется best-effort. Daily updater умеет health-check/rollback при неудачном обновлении.

## CI

GitHub Actions проверяет Python 3.11, 3.12 и 3.13. Основная matrix выполняет locked install, `pip check`, compileall и unit tests.

Отдельный quality job добавляет:

- Ruff correctness lint;
- formatter check для typed foundation;
- mypy для typed foundation;
- полный test suite под coverage;
- coverage gate `>=70%`;
- ShellCheck для `start.sh` и `scripts/*.sh`.

## Архитектура

```text
anime-db-bot/
├── bots/
│   ├── session_store.py
│   └── telegram/
│       ├── bot.py
│       ├── callbacks.py
│       ├── people_loading.py
│       ├── people_views.py
│       ├── people_portraits.py
│       ├── search_ui.py
│       ├── settings.py
│       ├── admin.py
│       ├── card/
│       └── transports/
├── core/
│   ├── identity.py
│   ├── source_keys.py
│   ├── capabilities.py
│   ├── settings.py
│   ├── source_errors.py
│   ├── http_client.py
│   ├── canonicalization.py
│   ├── contracts.py
│   └── models.py
├── mappings/
├── localization/
├── search/
├── services/
│   ├── app_context.py
│   ├── source_health.py
│   ├── identity_aggregator.py
│   ├── aggregation_merge.py
│   ├── direct_lookup.py
│   └── ...
├── sources/
├── tests/
├── scripts/
├── start.sh
└── README.md
```

## Оставшиеся архитектурные долги

После текущего refactor foundation основные долги уже не относятся к primary-ID или transport wiring. Наиболее заметные следующие шаги:

- полноценный `CharacterIdentity`: текущий cross-source character display merge всё ещё использует нормализованные варианты имени и не считается canonical identity;
- typed date/datetime values вместо части строковых дат в domain models;
- расширение persistent user/account/preferences/watch-state слоя поверх существующего repository boundary;
- дальнейшее повышение общего coverage и постепенное расширение mypy/formatter scope на legacy modules;
- richer audit metadata/history для manual mapping overrides.

Эти ограничения не меняют текущие non-regression contracts: source-independent identity, direct-only mapping safety, lazy sections, explicit provenance и scoped rate/session state.
