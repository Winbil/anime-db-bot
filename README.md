# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких баз данных.

Главный принцип проекта: **поиск, identity, metadata sources, агрегирование, локализация и UI конкретной платформы — отдельные слои**. У аниме больше нет обязательного «главного» ID одной базы: `AnimeIdentity` хранит граф внешних идентификаторов (`mal`, `anilist`, `shikimori` и будущие `anidb`, `kinopoisk` и другие) как равноправные связи.

## Что подключено

### Поиск

Единственная пользовательская команда поиска — `/anime`.

Быстрый режим `/anime <название>` параллельно использует Shikimori Search и MyAnimeList Search. `/anime` без аргументов показывает inline-выбор `Все`, MAL, Shikimori, AniList и переводит пользователя в короткоживущее user/chat-scoped состояние ожидания следующего сообщения. Состояние можно отменить через `/cancel`, и оно автоматически истекает.

Числовой аргумент рассматривается как direct external ID. `/anime 37430` проверяет этот ID во всех зарегистрированных identity-native metadata sources, а явный вариант вроде `/anime mal:37430` ограничивает direct lookup конкретной базой. При пошаговом выборе MAL/Shikimori/AniList обычный числовой ID проверяется только в выбранном источнике. Direct lookup построен через `source_key`/registry, поэтому будущие базы подключаются без MAL-specific веток в Telegram handlers.

Одинаковое числовое значение в двух разных базах само по себе не означает одну сущность: direct-ID результаты объединяются только по подтверждённым external-ID связям, которые реально вернули источники.

Текстовый search merge двухслойный:

1. conflict-safe merge по подтверждённым общим external IDs;
2. fallback по точному нормализованному romaji, если ID-граф ещё не связывает базы.

Конфликт двух разных ID одной и той же базы всегда запрещает склейку, в том числе через транзитивный «мост». Результаты без MAL ID сохраняются.

Перед Telegram-пагинацией `SearchService.collect()` формирует query-scoped relevant result set. Relevance policy учитывает display title, romaji, native-script и aliases, exact/prefix/token matches, русскую транслитерацию и консервативный similarity fallback. Если очередная полная upstream-страница уже не содержит релевантных кандидатов, дальнейший fetch этого provider останавливается. Есть также hard caps на глубину/количество результатов для защиты API quota.

После relevance filtering выполняются ID/title merge и dedupe. Telegram затем листает **зафиксированный merged result set локально**, поэтому на дальних страницах не подмешивается новый нерелевантный хвост API.

Поисковая выдача показывает один тайтл за раз: обложку/обложки, название, год и найденные external IDs. Inline-пагинация выглядит как `◀ 3/18 ▶`, а кнопка `Подробнее` открывает полноценную агрегированную карточку текущего `AnimeIdentity`. Если сбор остановлен hard cap или часть источников недоступна и точный итог не гарантирован, счётчик честно отображается как `3/18+`.

После выбора результата metadata собирается из всех доступных источников, независимо от того, какой provider нашёл результат.

### Source-independent identity

```text
SearchCandidate
      │
      ▼
AnimeIdentity
├── mal: ...
├── anilist: ...
├── shikimori: ...
└── future-source: ...
```

Ни один из этих ключей не является primary ID. Каждый metadata source получает целый `AnimeIdentity` и сам выбирает ID, который умеет использовать. Если первый успешно ответивший source обнаружил новый внешний ID, aggregator расширяет identity graph и даёт ранее неприменимым sources второй проход.

Например, результат может начать путь только с `anilist:10`, AniList metadata добавить `mal:20`, после чего MyAnimeList сможет подключиться без требования иметь MAL ID ещё на этапе поиска.

Best-effort resolver также может добавлять новые связи. Сейчас есть fallback MAL → Shikimori, потому что Shikimori search умеет вернуть оба ID; это только один resolver edge, а не глобальное правило identity.

### Metadata sources

- Shikimori;
- AniList;
- MyAnimeList.

Дополнительно используется **Jikan как MAL web-supplement**, а не как отдельная identity-база. Он живёт в отдельном локальном контейнере `anime-db-bot-Jikan`, получает уже подтверждённый `mal` ID и по запросу парсит публичные страницы MyAnimeList. В `AnimeIdentity` нового `jikan` ID нет; provenance хранится как `source=mal`, `backend=jikan`, а в UI этот слой называется `MAL (MyAnimeList) / Jikan`.

Сейчас через Jikan реализован только lazy-раздел **«Серии»**: список эпизодов грузится при открытии раздела, подробности отдельного эпизода — только при выборе серии. Никакой локальной индексации каталога MAL, MongoDB, Redis или Typesense для этого не используется.

`AnimeAggregator` объединяет названия, жанры, студии, даты, статусы, оценки, персонал и другие поля. Provenance сохраняется там, где он действительно нужен: внешние ID/URL, описания, source-specific варианты названий, staff/voices и портреты.

Чистые merge-функции вынесены в `services/aggregation_merge.py`, а identity-aware orchestration находится в `services/identity_aggregator.py`. `services/aggregator.py` оставлен только как compatibility import surface и больше не содержит MAL-primary реализации.

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

## Локализация и `/settings`

Интерфейс поддерживает ровно два языка:

- `ru` — Русский;
- `en` — English.

`/settings` открывает настройки пользователя. Сейчас там есть один пункт — **язык интерфейса**. Внутри доступны inline-кнопки `🇷🇺 Русский` и `🇬🇧 English`.

Выбор хранится по Telegram user ID в SQLite и переживает перезапуск процесса. По умолчанию используется:

```text
data/user_settings.sqlite3
```

Путь можно переопределить:

```env
USER_SETTINGS_DB_PATH=/data/user_settings.sqlite3
```

Это первый рабочий кусок будущей пользовательской БД. Repository читает только запись нужного пользователя и не загружает настройки всех пользователей в RAM.

### Locale-neutral domain model

Source adapters больше не записывают в `AnimeRecord` русские display-строки вроде `выходит`, `Весна`, `Фэнтези`. Вместо этого хранятся canonical values:

```text
status = airing
kind = tv
season = spring
genres = [fantasy, isekai]
source_materials = [light_novel]
```

Одна и та же `AggregatedAnime` затем может быть показана как:

```text
RU:
Статус: выходит
Сезон: Весна
Жанры: Фэнтези, Исекай
```

или:

```text
EN:
Status: Airing
Season: Spring
Genres: Fantasy, Isekai
```

без повторного обращения к metadata API.

Каталоги находятся в:

```text
localization/
├── catalog.py
├── data/
│   ├── aliases.json
│   └── source_values.json
└── locales/
    ├── ru.json
    └── en.json
```

`source_values.json` переводит enum конкретного API в canonical key. `aliases.json` отвечает за нормализацию жанров/ролей/studios. `ru.json` и `en.json` содержат UI и display labels.

Свободный текст источника, например описание аниме, **не переводится машинно**. Он остаётся в том языке, который отдал выбранный source.

## Имена людей и роли

`PersonCredit` хранит raw name variants и canonical роли, а не готовую строку для интерфейса. Renderer выбирает display-name под язык пользователя:

```text
RU: Дзюн Фукуяма (Jun Fukuyama, 福山 潤)
EN: Jun Fukuyama (福山 潤)
```

Это также предотвращает повторное вложенное форматирование имён при merge.

Динамические voice credits хранятся locale-neutral, например:

```text
voice_of::Rimuru Tempest
```

и превращаются в:

```text
RU: Озвучка: Rimuru Tempest
EN: Voice: Rimuru Tempest
```

## Ленивая загрузка персонала

Главная карточка metadata-only и не ждёт тяжёлые списки людей.

- Shikimori staff — при первом открытии staff-раздела;
- AniList staff — при первом открытии staff-раздела;
- AniList Japanese voice actors — при первом открытии voice-раздела;
- Shikimori original Japanese seiyuu — `anime roles -> character -> seyu`, тоже только по запросу UI.

Lazy people loaders тоже получают `AnimeIdentity`, поэтому AniList-only или Shikimori-only карточка не требует MAL ID для открытия персонала.

Данные вливаются в уже существующую `AggregatedAnime`, поэтому основная metadata карточки повторно не запрашивается.

Для Shikimori REST действует общий process-wide rate limiter и retry после HTTP 429 с `Retry-After`.

## Jikan container и обновления

Минимальный parser-service находится **в этом же репозитории**:

```text
compose.yml
jikan_service/
├── Dockerfile
├── composer.json
└── public/router.php
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Запуск вручную:

```bash
docker compose build jikan
docker compose up -d --no-build jikan
```

Контейнер называется `anime-db-bot-Jikan`, работает через host network из-за ограничений Docker subnet pool на текущем сервере, но PHP слушает только `127.0.0.1:${JIKAN_PORT:-8091}`. Наружу parser-service не публикуется.

`start.sh` проверяет контейнер и поднимает его при необходимости, но отказ Jikan не останавливает основной бот — раздел серий просто остаётся недоступен как отдельная degraded capability.

`update-jikan.sh` раз в сутки сравнивает установленную версию с последним стабильным GitHub release Jikan. Перед переключением он ждёт отсутствия активного Jikan-request lock, сохраняет старый image для rollback, собирает новый image, запускает и проверяет health/version. При ошибке цепочка повторяется ещё два раза; после трёх неудач возвращается старый image и новая попытка откладывается до следующей ежедневной проверки. После успешного запуска старый image удаляется.

Systemd unit-файлы коммитятся вместе с проектом; на сервере они подключаются к systemd как launcher для project-local script.

## Архитектура

```text
anime-db-bot/
├── bots/
│   ├── session_store.py
│   └── telegram/
│       ├── bot.py
│       ├── admin.py
│       ├── settings.py
│       ├── search_ui.py
│       ├── people_portraits.py
│       ├── card/
│       │   ├── constants.py
│       │   ├── handlers.py
│       │   ├── keyboards.py
│       │   ├── renderer.py
│       │   ├── selectors.py
│       │   ├── service.py
│       │   └── state.py
│       └── transports/
│           ├── official.py
│           └── tgapi.py
├── core/
│   ├── identity.py
│   ├── canonicalization.py
│   ├── contracts.py
│   ├── http_config.py
│   └── models.py
├── localization/
│   ├── catalog.py
│   ├── data/
│   └── locales/
├── search/
│   ├── registry.py
│   └── providers/
├── services/
│   ├── aggregation_merge.py
│   ├── identity_aggregator.py
│   ├── aggregator.py
│   ├── direct_lookup.py
│   ├── id_resolver.py
│   ├── search.py
│   ├── bans.py
│   ├── access_control.py
│   └── user_settings.py
├── sources/
├── tests/
├── start.sh
└── README.md
```

### Telegram platform layer

`bots/telegram/bot.py` — composition root и lifecycle Telegram implementation.

`bots/telegram/transports/official.py` и `tgapi.py` — реальные backend-реализации official Bot API и локального `tg-bot-api`. Они создают Bot/session, участвуют в health-check и shutdown lifecycle.

`bots/telegram/card/` — обычная anime-card логика. `people_portraits.py` содержит lazy people/portrait UI. `settings.py` отвечает за Telegram settings UI. `admin.py` содержит moderation middleware и admin-only команды.

`bots/` не считается синонимом Telegram: будущий Discord implementation можно добавить отдельным `bots/discord/`, не меняя `core/`, `localization/`, `search/`, `services/` и `sources/`.

## Поток данных

```text
Text search providers
      │
      ▼
provider pages
      │
      ▼
relevance filtering + irrelevant-tail stop
      │
      ▼
query-scoped SearchResultSet
      │
      ▼
ID merge -> romaji fallback -> dedupe
      │
      ▼
local Telegram preview pagination
      │
      └── Подробнее
              │
              ▼
          AnimeIdentity
              │
              ▼
       metadata sources
              │
              ├── discover extra external IDs
              │             │
              │             └── optional second source pass
              ▼
       AnimeAggregator
              │
              ▼
       AggregatedAnime
```

Direct-ID search joins the same pipeline at `AnimeIdentity`: each registered source receives its own source-local ID and only confirmed cross-ID edges can merge hits.

Карточки, search-preview sessions и пошаговый `/anime` flow привязаны к владельцу по Telegram user ID; pending input дополнительно привязан к chat ID. Другой пользователь или другой чат не может продолжить чужой flow.

## Кеши и runtime state

Search и anime-card callback sessions используют bounded in-memory storage со sliding TTL и LRU.

```env
TELEGRAM_SESSION_TTL_SECONDS=3600
ANIME_INPUT_TTL_SECONDS=300
SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
SEARCH_COLLECTION_PAGE_SIZE=20
SEARCH_COLLECTION_MAX_PAGES=4
SEARCH_COLLECTION_MAX_ITEMS=120
SEARCH_RELEVANCE_THRESHOLD=55
SEARCH_IRRELEVANT_TAIL_PAGES=1
ANILIST_PEOPLE_MAX_PAGES=4
ANILIST_PEOPLE_CACHE_TTL_SECONDS=21600
SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS=21600
SHIKIMORI_REST_MIN_INTERVAL_SECONDS=0.24
```

Краткоживущий callback/cache state очищается после restart. Пользовательский `locale` и registry известных пользователей хранятся в SQLite. Баны хранятся отдельно в `data/bans.sqlite3`.

## Telegram transport

`start.sh` всегда запускает:

```text
bots.telegram.bot
```

Сам `bot.py` выбирает transport:

- без `TELEGRAM_BOT_API_URL` — official `api.telegram.org`;
- с `TELEGRAM_BOT_API_URL` — локальный/self-hosted `tg-bot-api`.

Оба транспорта имеют общий lifecycle:

```text
create_bot()
check_health()
close()
```

## Зависимости и запуск

`requirements.lock` используется и локальным запуском, и CI.

```bash
cd anime-db-bot
git pull
./start.sh
```

`start.sh` создаёт/проверяет venv, устанавливает locked dependencies, запускает compile/test checks и затем стартует `bots.telegram.bot` в tmux.

## Тесты и CI

GitHub Actions проверяет Python 3.11, 3.12 и 3.13:

```bash
python -m compileall -q bots core localization search services sources tests
python -m unittest discover -s tests -v
```

Regression coverage включает:

- page-level search/cache contracts;
- query-scoped relevance collection и остановку нерелевантного хвоста;
- точный/неполный (`N`/`N+`) search result count;
- native-script/romaji/alias relevance;
- source-independent `AnimeIdentity`;
- search result без MAL ID;
- merge по AniList/Shikimori/другому external ID;
- transitive identity graph и защиту от conflict-merge;
- direct-ID lookup, source restriction и защиту от same-number false merge;
- двухфазное metadata aggregation с обнаружением новых IDs;
- отсутствие mutation исходного `SearchCandidate`;
- source resilience/capability preservation;
- Shikimori `character -> seyu` parsing;
- lazy people loading;
- source-keyed portraits;
- Telegram transport lifecycle;
- canonical RU/EN localization;
- одну domain model, рендерящуюся на RU и EN;
- raw person-name rendering без повторного вложения;
- persistent SQLite user locale settings и moderation storage.

## Известные архитектурные ограничения

Главные ещё не закрытые ограничения находятся во внешнем refactor-audit. Среди них:

- cross-ID resolver graph пока неполный: сейчас best-effort fallback явно реализован только для MAL → Shikimori; новые базы должны добавлять собственные resolver edges там, где это действительно нужно;
- нет typed capabilities/source errors/shared HTTP lifecycle;
- нет общего source-health/circuit breaker;
- часть старых source modules всё ещё содержит внутренние legacy helper/class boundaries, хотя активный registry уже использует identity-native adapters;
- кроме interface locale/known-user registry, остальное пользовательское состояние ещё не перенесено в persistent DB.
