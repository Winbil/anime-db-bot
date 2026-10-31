> **Проект создан с помощью AI:** при разработке этого проекта использовался искусственный интеллект.

<p align="center">
  <a href="../README.md">English</a> · <strong>Русский</strong> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

> Telegram-бот с независимым от конкретной базы поиском аниме и агрегацией метаданных из MyAnimeList/Jikan, AniList, Shikimori, Kitsu, AniDB и AniSearch.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` ищет аниме сразу в нескольких базах, разрешает подтверждённые cross-ID связи и собирает единую карточку, не назначая ни одну внешнюю базу главным источником истины.

Архитектура разделяет **поиск**, **identity**, **mappings**, **metadata sources**, **aggregation**, **localization** и **platform UI**. Для staff/сэйю заранее в фоне строится лёгкий manifest из ID, имени и роли с точным total, а портреты обогащаются отдельными глобальными batch по 50; остальные тяжёлые данные остаются lazy.

## Возможности

- **Мульти-source поиск** — Shikimori, MyAnimeList, AniList и Kitsu работают через единый `/anime` flow.
- **Source-independent identity** — `AnimeIdentity` хранит равноправные external IDs без глобального primary ID.
- **Консервативный cross-ID mapping** — runtime mapping direct-only, conflict-aware, с provenance и аудируемыми manual overrides.
- **Агрегированная карточка** — данные успешных metadata sources нормализуются и объединяются с сохранением provenance.
- **Manifest + lazy enrichment** — для staff/сэйю лёгкие ID/имена/роли prefetched для точного roster, портреты догружаются глобальными batch (по умолчанию 50), а персонажи, скриншоты, подробная популярность, descriptions/background, трейлеры и эпизоды остаются lazy.
- **Общий resilience layer** — typed source errors, retry, circuit breaker, half-open recovery, rate limits и shared HTTP lifecycle.
- **Persistent platform-scoped settings** — locale, known users и moderation state хранятся в SQLite.
- **Семь языков UI** — английский является default/fallback; русский, японский, немецкий, испанский, французский и итальянский выбираются через `/settings`.
- **Релизные данные и прогноз серий** — агрегируются возрастной рейтинг, статус выхода, количество вышедших/всего серий и дата следующей серии из источников; для выходящих TV-аниме с известным total все оставшиеся серии получают явно помеченный недельный прогноз.
- **Production-oriented CI** — Python 3.11–3.14, Ruff, formatter, mypy scope, coverage gate и ShellCheck.

## Возможности источников

| Источник | Поиск | Metadata | Люди | Персонажи | Трейлеры | Эпизоды | Скриншоты | Популярность | Описание |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu подключён как identity-native публичный JSON:API источник. Обычные read-only GET-запросы не требуют OAuth; подтверждённые Kitsu ID уже участвуют в `mappings.db`, а сам Kitsu возвращает прямые mappings к MAL/AniList/AniDB. Сейчас Kitsu даёт поиск, metadata, popularity, description, эпизоды и YouTube-трейлер при наличии. People/characters намеренно пока не заявлены как capability, потому что эти relationships у Kitsu часто неполные.

AniDB опционален и включается только при настроенном `ANIDB_CLIENT`. Jikan **не является отдельной identity-базой**: это локальный backend MAL для данных, которых нет в официальном MAL API. Licensors для main card и lazy popularity statistics теперь используют разные local endpoints, поэтому score distribution больше не парсится на initial card path. AniSearch подключён как identity-native источник Database API через подтверждённые `anisearch` edges из mappings.db. Публичного query-search endpoint у AniSearch нет, поэтому он не добавляется в быстрый `/anime <title>` поиск. Так как AniSearch помещает ID и `/full` в одну строгую rate-limit группу, источник делает один cached `/full` запрос на тайтл, но не подмешивает heavy fields в initial aggregation; people/characters/episodes затем используют тот же payload без второго сетевого ожидания. Используются английская, японская, немецкая, испанская, французская и итальянская локализации AniSearch: локализованные названия/синонимы, synopsis, названия эпизодов, региональные licensors и voice credits. Без токена запросы ID-family дополнительно выдерживают документированный интервал 10 секунд (5 секунд с валидным токеном); synopsis от AniSearch всегда сопровождается требуемой прямой ссылкой на запись AniSearch. Поддержка SkipDB сохранена в кодовой базе как dormant IMDb-backed provider, но намеренно не зарегистрирована в runtime: текущее покрытие anime skip-segments слишком мало, чтобы показывать источник пользователю. Parser/settings/tests остаются на месте, чтобы SkipDB можно было быстро включить позже, если покрытие заметно вырастет. Данные SkipDB распространяются по ODbL 1.0 + reciprocity.

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
      ├── Kitsu
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
/anime kitsu:<id>
```

`/anime <title>` параллельно опрашивает зарегистрированные search providers и до Telegram-пагинации собирает bounded query-scoped result set. Relevance учитывает titles, aliases, native/romaji варианты, prefix/token matches, transliteration и консервативный similarity fallback.

Hard caps защищают upstream quotas. Если бот не может доказать, что итоговое число результатов окончательное, UI показывает неполный count честно, а не выдаёт его за точный.

`/anime` без аргументов открывает интерактивный выбор источников. Pending input привязан к паре user/chat, автоматически истекает и отменяется через `/cancel`.

`/anime` также поддерживает поиск по изображению: можно прикрепить картинку к команде или передать публичную ссылку на изображение. Бот показывает только те image-search сервисы, у которых сейчас доступна квота: trace.moe, What Anime Is This или оба сразу. Одинаковые ответы объединяются строго по подтверждённому AniList ID, а кандидаты показываются постранично как в обычном поиске; полная карточка открывается только после нажатия **Подробнее**. В превью остаются источник совпадения, similarity, серия и таймкод. Кнопка **Нет нужного тайтла?** позволяет повторить поиск с новым выбором сервиса или отменить его. Загруженные raster-изображения перед отправкой нормализуются в JPEG.

## Lazy-разделы карточки

Основная карточка остаётся metadata-first. Только по запросу загружаются:

- staff и creators;
- voice actors, включая помеченные языком дубляжные credits AniSearch;
- characters и portraits;
- screenshots;
- подробная popularity/ranking statistics;
- descriptions и source background;
- trailers/promos;
- episodes.

Японские voice credits остаются исходной дорожкой без языкового суффикса. Дубляжные credits AniSearch сохраняются с явными суффиксами `[EN]`, `[DE]`, `[ES]`, `[FR]` или `[IT]`, поэтому они не маскируются под оригинальный японский cast. Localization/ADR staff исключается из основного production staff.

## Требования и поддержка ОС

Python-runtime рассчитан на **Linux, macOS и нативный Windows** с Python **3.11, 3.12, 3.13 или 3.14**. GitHub Actions прогоняет полный unit suite на всех трёх семействах ОС для каждой поддерживаемой версии Python.

- **Linux** — основная production-платформа. Кроссплатформенный launcher должен работать на большинстве современных дистрибутивов при наличии поддерживаемого CPython. `start.sh` остаётся Linux-oriented helper для существующего production-запуска через `tmux`.
- **macOS** — поддерживается через Python launcher; для удобства есть `start.command`. `systemd`-юниты на macOS не применяются.
- **Windows native** — поддерживается через Python launcher, `start.ps1` или `start.cmd`; WSL не требуется.
- **Docker + Docker Compose** — необязательны на всех ОС и нужны только для локального Jikan supplement. Без Docker официальный MAL продолжает работать, отключаются лишь Jikan-only дополнения.
- **systemd** — необязательная Linux-only обвязка из `deploy/systemd/`.

Для быстрой проверки окружения можно выполнить `python scripts/project.py doctor` активным Python-интерпретатором.

## Быстрый старт

Сначала клонируйте репозиторий:

```text
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Канонический launcher — `scripts/project.py`. Он создаёт `.venv`, устанавливает locked dependencies, создаёт отсутствующие конфиги из example-файлов без перезаписи существующих значений и сам выбирает `bin/python` на Unix или `Scripts/python.exe` на Windows.

Linux / macOS:

```bash
python3 scripts/project.py setup
# Добавьте как минимум BOT_TOKEN в .env.d/telegram.env.
python3 scripts/project.py check
python3 scripts/project.py run       # foreground
python3 scripts/project.py start     # background + PID file
```

Windows PowerShell / Command Prompt:

```powershell
py -3 scripts\project.py setup
# Добавьте как минимум BOT_TOKEN в .env.d\telegram.env.
py -3 scripts\project.py check
py -3 scripts\project.py run
.\start.ps1                         # background
```

Для Command Prompt есть `start.cmd`, для macOS — `./start.command`. Background-процесс, запущенный общим launcher, управляется командами:

```text
python scripts/project.py status
python scripts/project.py stop
python scripts/project.py restart
```

Linux production может по-прежнему использовать `./start.sh`, сохраняя текущий detached `tmux` workflow. Основные runtime-логи остаются в `logs/YYYY.MM.DD/`, а generic background launcher дополнительно пишет stdout/stderr в `logs/launcher.log`.

Runtime-логи разделены по назначению в `logs/YYYY.MM.DD/`: `bot.log` содержит события приложения/runtime, `users.log` — действия пользователей Telegram, `api.log` — outbound source/API/retry/health события, а `errors.log` дополнительно дублирует все записи `ERROR+` для быстрой диагностики. После локальной полуночи следующая запись автоматически попадёт в новый дневной каталог без перезапуска бота.

## Конфигурация

Все runtime environment settings централизованно читаются в `core/settings.py`. Для новой установки `.env.example.d/` копируется в `.env.d/`. Загружаются только фиксированные файлы `telegram.env`, `sources.env`, `timestamps.env`, `rate-limits.env`, `mappings.env`, `storage.env`, `logging.env` и `runtime.env`; случайные файлы вроде `backup.env` игнорируются. Дубли ключей между project config files останавливают запуск, а реальные переменные окружения процесса имеют наивысший приоритет. Монолитный `.env` сохранён только для переходной совместимости.

### Основные переменные

| Переменная | Обязательна | Назначение |
| --- | :---: | --- |
| `BOT_TOKEN` | Да | Telegram bot token от BotFather. |
| `MAL_CLIENT_ID` | Рекомендуется | Включает официальный MyAnimeList search и metadata. |
| `ANIDB_CLIENT` | Нет | Включает AniDB HTTP API metadata/people/episodes. |
| `ANIDB_CLIENT_VERSION` | Нет | Версия зарегистрированного AniDB HTTP client; default `1`. |
| `ANILIST_ACCESS_TOKEN` | Нет | Optional AniList token для authenticated access. |
| `KITSU_API_URL` | Нет | Base URL публичного Kitsu JSON:API; default `https://kitsu.io/api/edge`. |
| `TRACE_MOE_API_KEY` | Нет | Optional API key trace.moe; без ключа используется free-mode, фактическая квота читается из `/me`. |
| `WHATANIMEISTHIS_API_KEY` | Нет | Optional API key What Anime Is This; без ключа используется guest-mode. |
| `IMAGE_SEARCH_DB_PATH` | Нет | SQLite для persistent учёта ограниченной image-search квоты. |
| `ADMIN_TELEGRAM_USER_IDS` | Нет | Telegram user IDs администраторов. |
| `TELEGRAM_BOT_API_URL` | Нет | Custom/self-hosted Telegram Bot API endpoint. |
| `TELEGRAM_BOT_API_LOCAL_FILE_ROOT` | Нет | Host-каталог, соответствующий `/var/lib/telegram-bot-api` внутри контейнера local Bot API; нужен для чтения локальных `file_path`. |
| `USER_SETTINGS_DB_PATH` | Нет | SQLite для user settings и known-user registry. |
| `BANS_DB_PATH` | Нет | SQLite для moderation bans. |
| `MAPPINGS_DB_PATH` | Нет | Runtime cross-ID mapping database. |

Не коммитьте `.env`, `.env.d/`, `.proxies.d/`, bot/access tokens, пароли, credentials прокси и другие приватные данные.

### Прокси по источникам

Исходящий трафик можно маршрутизировать отдельно для каждого runtime-источника через `.proxies.d/`. Для каждого source используется свой фиксированный TOML-файл, а `telegram.toml` относится к самому Telegram-боту. Шаблоны лежат в `.proxies.example.d/`. Поддерживаются `http`, `socks4` и `socks5`.

```toml
enabled = true

[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://user:password@127.0.0.1:1080"

[[proxy]]
name = "backup"
enabled = false
priority = 10
url = "http://127.0.0.1:8080"
```

Профили полностью независимы: `mal.toml` действует только на MAL, `anilist.toml` — только на AniList и т.д. Несколько включённых записей выбираются round-robin, а при сетевой/proxy-ошибке запрос пробует оставшиеся включённые прокси. Одинаковые URL разрешены, если у записей разные `name`, поэтому повторением одного endpoint можно намеренно увеличить его вес в ротации. `enabled = false` выключает либо весь профиль, либо конкретную запись. Если у профиля есть хотя бы один активный proxy, при отказе всех прокси **нет скрытого fallback на прямое соединение**; напрямую source ходит только когда активных proxy нет. Изменения proxy-конфигов применяются после перезапуска бота. Если в `telegram.toml` есть активные прокси, именно этот бот намеренно обходит настроенный локальный/общий `telegram-bot-api` и подключается к официальному `api.telegram.org` через свой proxy-pool — так прокси не влияет на другие боты, использующие тот же локальный сервер. `jikan.toml` тоже обрабатывается специально: Python → локальный Jikan остаётся direct, а выбранный proxy передаётся внутрь Jikan и применяется уже к его исходящему запросу в MyAnimeList.

Фиксированные профили: `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `bahamut`, `baha_anime_skip`, `skipdb`, `trace_moe`, `whatanimeisthis`. Посторонние TOML-файлы игнорируются. `.proxies.d/` gitignored, потому что в URL могут быть логин/пароль; `start.sh` выставляет каталогу mode `700`, известным файлам — `600`.

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
/anime kitsu:<id>
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
- `ja` — 日本語;
- `de` — Deutsch;
- `es` — Español;
- `fr` — Français;
- `it` — Italiano.

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
│   ├── providers/       # MAL, AniList, Shikimori, Kitsu, AniDB, AniSearch и Jikan adapters
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

Кроссплатформенные команды обслуживания mappings:

```text
python scripts/project.py mappings --status
python scripts/project.py mappings --override-list
python scripts/project.py mappings --override-history
```

Unix-wrapper `./scripts/update-mappings.sh` сохранён для существующих deployment'ов.

## Разработка

На всех поддерживаемых ОС используется один launcher:

```text
python scripts/project.py setup --dev
python scripts/project.py check
python scripts/project.py doctor
```

На Windows вместо `python` можно использовать `py -3`. Unix-файлы `./scripts/setup.sh` и `./scripts/check.sh` являются convenience-wrapper'ами над тем же Python-кодом. Нативный Python из venv находится в `.venv/bin/python` на Unix и `.venv\Scripts\python.exe` на Windows.

GitHub Actions требует успешного прохождения полного unit suite на **Ubuntu, macOS и Windows** для Python 3.11, 3.12, 3.13 и 3.14. Каждый matrix job также запускает cross-platform launcher doctor. Linux quality job дополнительно запускает Ruff, formatter check typed foundation, mypy typed foundation, полный suite с coverage gate `>=70%` и ShellCheck для Unix-wrapper'ов.

## Контрибьюторы

- [OpenAI Codex](https://github.com/apps/openai-codex) — официальный GitHub App Codex; помощь в разработке и реализации проекта с использованием ИИ.

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
- [Kitsu](https://kitsu.app/) — публичный read-only JSON:API; для обычных GET-запросов OAuth не нужен
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) — Database API metadata; attribution and synopsis-link requirements apply
- [SkipDB](https://skipdb.tv/) — skip-segment data under ODbL 1.0 + reciprocity

Cross-ID mapping строится из нескольких community datasets. Для каждого upstream service/dataset действуют его собственные условия использования, rate limits и требования к attribution.

Публичные read-only GET-запросы Kitsu используются без OAuth credentials. Runtime применяет собственные консервативные rate limits и не полагается на недокументированный серверный лимит.

Read-only запросы к AniSearch Database API не требуют OAuth. `ANISEARCH_APP_ID` и `ANISEARCH_APP_SECRET` — необязательные OAuth-реквизиты приложения для будущих пользовательских функций AniSearch; с обычными запросами базы они не отправляются.
