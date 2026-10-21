# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких баз данных.

Главный принцип проекта: **поиск, metadata sources, агрегирование, локализация и UI конкретной платформы — отдельные слои**. Канонический ID между интеграциями пока остаётся MAL ID.

## Что подключено

### Поиск

Обычный `/anime <название>` параллельно использует Shikimori Search и MyAnimeList Search. Результаты объединяются по MAL ID.

Legacy-команда `/search` пока позволяет явно выбрать MAL, Shikimori, AniList, несколько providers или все сразу. В roadmap она будет удалена, а выбор поисковых источников перейдёт в `/anime`.

После выбора результата metadata собирается из всех доступных источников, независимо от того, какой provider нашёл результат.

### Metadata sources

- Shikimori;
- AniList;
- MyAnimeList.

`AnimeAggregator` объединяет названия, жанры, студии, даты, статусы, оценки, персонал и другие поля. Provenance сохраняется там, где он действительно нужен: внешние ID/URL, описания, source-specific варианты названий, staff/voices и портреты.

## Команды

```text
/start
/ping
/settings
/anime <название>
/search <название>
/search mal <название>
/search shikimori <название>
/search anilist <название>
/search all <название>
/search mal,shikimori <название>
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

Данные вливаются в уже существующую `AggregatedAnime`, поэтому основная metadata карточки повторно не запрашивается.

Для Shikimori REST действует общий process-wide rate limiter и retry после HTTP 429 с `Retry-After`.

## Архитектура

```text
anime-db-bot/
├── bots/
│   ├── session_store.py
│   └── telegram/
│       ├── bot.py
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
│   ├── aggregator.py
│   ├── id_resolver.py
│   ├── search.py
│   └── user_settings.py
├── sources/
├── tests/
├── start.sh
└── README.md
```

### Telegram platform layer

`bots/telegram/bot.py` — composition root и lifecycle Telegram implementation.

`bots/telegram/transports/official.py` и `tgapi.py` — реальные backend-реализации official Bot API и локального `tg-bot-api`. Они создают Bot/session, участвуют в health-check и shutdown lifecycle.

`bots/telegram/card/` — обычная anime-card логика. `people_portraits.py` содержит lazy people/portrait UI. `settings.py` отвечает за Telegram settings UI.

`bots/` не считается синонимом Telegram: будущий Discord implementation можно добавить отдельным `bots/discord/`, не меняя `core/`, `localization/`, `search/`, `services/` и `sources/`.

## Поток данных

```text
Search provider
      │
      ▼
SearchCandidate
      │
      ▼
metadata sources
      │
      ▼
AnimeAggregator
      │
      ▼
AggregatedAnime
(locale-neutral canonical values)
      │
      ├── locale=ru
      │      ▼
      │   Russian renderer
      │
      └── locale=en
             ▼
          English renderer
```

Карточки и search sessions привязаны к владельцу по Telegram user ID. Другой пользователь не может продолжить чужой callback flow.

## Кеши и runtime state

Search и anime-card callback sessions используют bounded in-memory storage со sliding TTL и LRU.

```env
TELEGRAM_SESSION_TTL_SECONDS=3600
SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
ANILIST_PEOPLE_MAX_PAGES=4
ANILIST_PEOPLE_CACHE_TTL_SECONDS=21600
SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS=21600
SHIKIMORI_REST_MIN_INTERVAL_SECONDS=0.24
```

Краткоживущий callback/cache state очищается после restart. Пользовательский `locale` хранится отдельно в SQLite и сохраняется.

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

- поиск, cache и pagination contracts;
- cross-ID enrichment;
- source resilience/capability preservation;
- Shikimori `character -> seyu` parsing;
- lazy people loading;
- source-keyed portraits;
- Telegram transport lifecycle;
- canonical RU/EN localization;
- одну domain model, рендерящуюся на RU и EN;
- raw person-name rendering без повторного вложения;
- persistent SQLite user locale settings.

## Известные архитектурные ограничения

Главные ещё не закрытые ограничения находятся во внешнем refactor-audit. Среди них:

- MAL ID пока остаётся обязательной общей identity;
- fused search pagination может терять overflow;
- нет typed capabilities/source errors/shared HTTP lifecycle;
- нет общего source-health/circuit breaker;
- кроме interface locale, остальное пользовательское состояние ещё не перенесено в persistent DB;
- legacy `/search` ещё не удалён.
