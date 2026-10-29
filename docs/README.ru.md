> **Проект создан с помощью AI:** при разработке этого проекта использовался искусственный интеллект.

<p align="center">
  <a href="../README.md">English</a> · <strong>Русский</strong> · <a href="README.ja.md">日本語</a>
</p>

# anime-db-bot

> Telegram-бот с независимым от конкретной базы поиском аниме и агрегацией метаданных из MyAnimeList/Jikan, AniList, Shikimori и AniDB.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` ищет аниме сразу в нескольких базах, разрешает подтверждённые cross-ID связи и собирает единую карточку, не назначая ни одну внешнюю базу главным источником истины.

Архитектура разделяет **поиск**, **identity**, **mappings**, **metadata sources**, **aggregation**, **localization** и **platform UI**. Тяжёлые данные — портреты, персонажи, трейлеры и эпизоды — загружаются лениво только после соответствующего действия пользователя.

## Возможности

- **Мульти-source поиск** — Shikimori, MyAnimeList и AniList работают через единый `/anime` flow.
- **Source-independent identity** — `AnimeIdentity` хранит равноправные external IDs без глобального primary ID.
- **Консервативный cross-ID mapping** — runtime mapping direct-only, conflict-aware, с provenance и аудируемыми manual overrides.
- **Агрегированная карточка** — данные успешных metadata sources нормализуются и объединяются с сохранением provenance.
- **Lazy-разделы** — люди, портреты, персонажи, трейлеры и эпизоды загружаются по требованию.
- **Общий resilience layer** — typed source errors, retry, circuit breaker, half-open recovery, rate limits и shared HTTP lifecycle.
- **Persistent platform-scoped settings** — locale, known users и moderation state хранятся в SQLite.
- **Три языка UI** — английский является default/fallback, русский и японский выбираются через `/settings`.
- **Production-oriented CI** — Python 3.11–3.14, Ruff, formatter, mypy scope, coverage gate и ShellCheck.

## Возможности источников

| Источник | Поиск | Metadata | Люди | Персонажи | Трейлеры | Эпизоды |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ |

AniDB опционален и включается только при настроенном `ANIDB_CLIENT`. Jikan **не является отдельной identity-базой**: это локальный backend MAL для данных, которых нет в официальном MAL API.

## Как это работает

```text
Telegram /anime
      │
      ▼
SearchService
      │
      ▼
SearchCandidate
      │
      ▼
AnimeIdentity  ◄──── disk-backed mappings.db
      │                + live MAL → Shikimori fallback
      ▼
AnimeAggregator
      │
      ├── Shikimori
      ├── AniList
      ├── MAL / Jikan
      └── AniDB (optional)
      │
      ▼
AggregatedAnime
      │
      ▼
Telegram card + lazy sections
```

### Правила identity

У `AnimeIdentity` нет primary ID. Совпадение числовых ID в разных базах никогда само по себе не считается доказательством одной сущности.

Cross-source merge работает консервативно:

1. общий подтверждённый external ID является сильным identity evidence;
2. конфликт ID одного provider запрещает merge;
3. text search может использовать ограниченный exact normalized romaji fallback только при отсутствии same-provider conflict;
4. direct-ID lookup не использует title-only merge;
5. runtime mappings direct-only и не выполняют произвольный recursive traversal через TVDB/TMDB-подобные цепочки.

Полный enriched identity сохраняется для внутренней маршрутизации и lazy-capabilities. В видимом ID-блоке карточки показываются только ID metadata sources, которые реально участвовали в сборке этой карточки.

## Поиск

Единственная пользовательская команда поиска — `/anime`.

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
```

`/anime <title>` параллельно опрашивает зарегистрированные search providers и до Telegram-пагинации собирает bounded query-scoped result set. Relevance учитывает titles, aliases, native/romaji варианты, prefix/token matches, transliteration и консервативный similarity fallback.

Hard caps защищают upstream quotas. Если бот не может доказать, что итоговое число результатов окончательное, UI показывает неполный count честно, а не выдаёт его за точный.

`/anime` без аргументов открывает интерактивный выбор источников. Pending input привязан к паре user/chat, автоматически истекает и отменяется через `/cancel`.

## Lazy-разделы карточки

Основная карточка остаётся metadata-first. Только по запросу загружаются:

- staff и creators;
- оригинальные японские voice actors;
- characters и portraits;
- trailers/promos;
- episodes.

Иностранные дубляжные роли не смешиваются с оригинальным японским voice list. Localization/ADR staff исключается из основного production staff.

## Требования

Рекомендуемое окружение:

- Linux server;
- Python **3.11, 3.12, 3.13 или 3.14**;
- Git;
- `tmux` для bundled `start.sh`;
- Docker + Docker Compose для опционального локального Jikan supplement.

Без Docker бот также работает: официальный MAL API остаётся доступным, а Jikan-only дополнения отключаются.

## Быстрый старт

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot

cp .env.example .env
# Отредактируйте .env и как минимум добавьте BOT_TOKEN.

./scripts/setup.sh
./scripts/check.sh
./start.sh
```

`start.sh` запускает Telegram-бота в detached `tmux` session и пытается поднять локальный Jikan container, если Docker Compose доступен.

```bash
tmux attach -t anime-db-bot
TODAY="$(date '+%Y.%m.%d')"
tail -f "logs/$TODAY/bot.log"
tail -f "logs/$TODAY/users.log"
tail -f "logs/$TODAY/api.log"
```

Runtime-логи разделены по назначению в `logs/YYYY.MM.DD/`: `bot.log` содержит события приложения/runtime, `users.log` — действия пользователей Telegram, `api.log` — outbound source/API/retry/health события, а `errors.log` дополнительно дублирует все записи `ERROR+` для быстрой диагностики. После локальной полуночи следующая запись автоматически попадёт в новый дневной каталог без перезапуска бота.

## Конфигурация

Все runtime environment settings централизованно читаются в `core/settings.py`. Полный список параметров и безопасных defaults находится в `.env.example`.

### Основные переменные

| Переменная | Обязательна | Назначение |
| --- | :---: | --- |
| `BOT_TOKEN` | Да | Telegram bot token от BotFather. |
| `MAL_CLIENT_ID` | Рекомендуется | Включает официальный MyAnimeList search и metadata. |
| `ANIDB_CLIENT` | Нет | Включает AniDB HTTP API metadata/people/episodes. |
| `ANIDB_CLIENT_VERSION` | Нет | Версия зарегистрированного AniDB HTTP client; default `1`. |
| `ANILIST_ACCESS_TOKEN` | Нет | Optional AniList token для authenticated access. |
| `ADMIN_TELEGRAM_USER_IDS` | Нет | Telegram user IDs администраторов. |
| `TELEGRAM_BOT_API_URL` | Нет | Custom/self-hosted Telegram Bot API endpoint. |
| `USER_SETTINGS_DB_PATH` | Нет | SQLite для user settings и known-user registry. |
| `BANS_DB_PATH` | Нет | SQLite для moderation bans. |
| `MAPPINGS_DB_PATH` | Нет | Runtime cross-ID mapping database. |

Не коммитьте `.env`, bot/access tokens, пароли и другие приватные credentials.

### AniDB

Интеграция использует AniDB HTTP API. Нужны зарегистрированные **client name и version**, а не пароль AniDB-аккаунта.

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

AniDB XML кешируется на диске, а network requests сериализуются с дополнительным минимальным интервалом между обращениями.

### MAL / Jikan

MAL остаётся identity source. Jikan — локальный supplemental backend и не создаёт `jikan` identity key.

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Сбой Jikan не делает официальный MAL search/metadata недоступным.

## Команды

### Пользовательские

```text
/start
/ping
/settings
/anime
/anime <title>
/anime <external_id>
/anime mal:<id>
/anime anilist:<id>
/anime shikimori:<id>
/cancel
```

### Административные

```text
/users
/source_health
/ban <user_id> [seconds] [reason]
/unban <user_id>
/mapping_overrides
/mapping_history [limit]
/mapping_set <accept|reject> <source_provider> <source_id> <target_provider> <target_id> <reason>
/mapping_delete <source_provider> <source_id> <target_provider> <target_id> <reason>
/mapping_confirm <token>
/mapping_cancel <token>
```

Mapping mutations двухэтапные: `/mapping_set` и `/mapping_delete` создают короткоживущий pending mutation, а реальное изменение БД происходит только после `/mapping_confirm <token>`. Audit history сохраняет Telegram admin, который выполнил изменение.

## Локализация

Domain model locale-neutral. Source adapters приводят upstream status/type/season/genre/role к canonical keys, а перевод выполняется только на этапе rendering.

Поддерживаются:

- `en` — English (**default и fallback**);
- `ru` — Русский;
- `ja` — 日本語.

Существующие пользователи сохраняют явно выбранный locale. Новые пользователи, отсутствующие settings, неизвестные locales и отсутствующие translation keys используют английский fallback.

Свободный текст источников, например anime descriptions, машинно не переводится. Подробнее: [`localization/README.md`](../localization/README.md).

## Persistence

Разные типы state разделены:

- user settings и known users — SQLite, scoped по `(platform, user_id)`;
- bans — отдельный persistent SQLite store;
- `mappings.db` — disk-backed cross-ID resolver;
- AniDB XML — disk cache;
- Telegram search/card callback sessions — bounded in-memory TTL/LRU state.

Legacy user settings до platform scoping мигрируют как Telegram records без изменения сохранённого locale.

## Resilience и rate limiting

Outbound HTTP использует shared `httpx.AsyncClient`, которым владеет `AppContext`. Source failures нормализуются в typed errors и проходят через общий retry/circuit-breaker layer.

Поддерживаются transient/non-transient handling, bounded retries, cooldown, circuit breaker и ровно один half-open recovery probe.

Personal Telegram limits scoped по `(platform,user_id)`. Admin может обходить personal limiter, но **никогда** не обходит upstream provider safety limits.

## Архитектура

```text
anime-db-bot/
├── bots/telegram/
│   ├── card/            # runtime карточки, feature-handlers, UI primitives и views
│   │   ├── features/    # персонажи, эпизоды, скриншоты, трейлеры
│   │   ├── runtime/     # handlers, session state и wiring карточки
│   │   ├── ui/          # клавиатуры, selectors и constants
│   │   └── views/       # renderers и представление секций
│   ├── people/          # lazy-загрузка людей, портреты и views
│   ├── search/          # Telegram search handlers/UI
│   └── transports/      # официальный и self-hosted Bot API transport
├── core/                # contracts, models, identity, settings, HTTP, errors
├── localization/        # locale catalogs и canonical localization data
├── mappings/            # cross-ID database, importers, resolver, updater
├── search/              # provider-facing search adapters и registry
├── services/
│   ├── aggregation/     # metadata aggregation и merge policy
│   ├── identity/        # direct lookup и cross-source identity resolution
│   ├── media/           # characters, episodes, people и trailers
│   ├── runtime/         # AppContext, source health и runtime rate-limit policy
│   ├── search/          # search orchestration и query expansion
│   └── users/           # access control, bans и persistent user settings
├── sources/
│   ├── providers/       # MAL, AniList, Shikimori, AniDB и Jikan adapters
│   └── runtime/         # source catalog, registries и resilience wrappers
├── tests/               # unit, integration, wiring и regression tests
├── jikan_service/       # локальный Jikan/MAL supplement service
├── scripts/             # setup, checks и maintenance helpers
└── deploy/systemd/      # optional maintenance units
```

`services/runtime/app_context.py` — application composition root. Production runtime dependencies должны принадлежать ему, а не создаваться как import-time service singletons.

Подробнее: [`docs/app-context.md`](app-context.md).

## Cross-ID mappings

Updater потоково загружает несколько внешних datasets в SQLite, хранит provenance/evidence/conflicts, валидирует новую БД и атомарно заменяет старую. Полный граф не загружается в RAM.

Manual directional overrides поддерживают `accept`/`reject`, author/reason/timestamp и append-only history.

```bash
./scripts/update-mappings.sh
.venv/bin/python -m mappings --status
.venv/bin/python -m mappings --override-list
.venv/bin/python -m mappings --override-history
```

## Разработка

```bash
./scripts/setup.sh
./scripts/check.sh
```

Дополнительные команды:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bots core localization mappings search services sources tests
.venv/bin/python -m pip check
```

GitHub Actions требует успешное прохождение Python 3.11, 3.12, 3.13 и 3.14. Quality job также запускает Ruff, formatter check typed foundation, mypy typed foundation, полный suite с coverage gate `>=70%` и ShellCheck.

## Участие в разработке

Pull requests приветствуются. Перед изменениями прочитайте [CONTRIBUTING.md](../CONTRIBUTING.md) и соблюдайте [Code of Conduct](../CODE_OF_CONDUCT.md). Для bug reports и feature requests используйте issue forms репозитория.

## Безопасность

- `.env` и credentials должны оставаться вне version control.
- Logs разделены на дневные `bot/users/api/errors` файлы, по умолчанию используют secret redaction, correlation ID для каждого update, timestamps в локальной timezone runtime и ограниченную ротацию каждого файла. `LOG_REDACT_SECRETS=0` намеренно полностью отключает маскирование для локальной диагностики и может записать credentials verbatim; на shared/public logs оставляйте его включённым.
- Admin-only actions должны оставаться за access-control layer.
- Self-hosted Telegram Bot API, будущий metrics endpoint и будущий external API нельзя публиковать наружу без явных authentication/network controls.
- Mapping overrides аудируются, потому что ошибочный identity edge способен затронуть несколько capabilities.

Правила безопасного сообщения об уязвимостях описаны в [SECURITY.md](../SECURITY.md). Не публикуйте credentials, tokens или private deployment details в публичном issue.

## Статус проекта

Проект активно развивается. Уже реализованы основной Telegram search/card flow, identity model, mapping database, multi-source aggregation, localization, lazy capabilities, persistence, resilience и CI foundation. Structured discovery/search filters, user account integrations, notifications, monitoring/Prometheus metrics, external API/Mini App и дополнительные sources остаются в планах.

## Лицензия

Проект распространяется по [Apache License 2.0](../LICENSE). Код можно использовать, изменять и распространять на условиях лицензии; обязательные notices должны сохраняться, а существенные изменения — отмечаться в предусмотренных лицензией случаях.

## Источники данных и благодарности

Проект интегрируется с данными и API:

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)

Cross-ID mapping строится из нескольких community datasets. Для каждого upstream service/dataset действуют его собственные условия использования, rate limits и требования к attribution.
