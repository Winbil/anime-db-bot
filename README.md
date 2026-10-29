> **AI-assisted project:** This project was developed with the help of AI.

<p align="center">
  <strong>English</strong> · <a href="docs/README.ru.md">Русский</a> · <a href="docs/README.ja.md">日本語</a>
</p>

# anime-db-bot

> Identity-native Telegram anime search and metadata aggregation across MyAnimeList/Jikan, AniList, Shikimori, and AniDB.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](LICENSE)

`anime-db-bot` searches multiple anime databases, resolves confirmed cross-database identities, and builds one source-independent card without treating any external database as the canonical source of truth.

The project is designed around explicit boundaries between **search**, **identity**, **mappings**, **metadata sources**, **aggregation**, **localization**, and **platform UI**. Expensive data such as staff portraits, characters, trailers, and episodes is loaded lazily only when the user opens the corresponding section.

## Highlights

- **Multi-provider search** — Shikimori, MyAnimeList, and AniList are queried through one `/anime` flow.
- **Source-independent identity** — `AnimeIdentity` stores peer external IDs; there is no global primary database ID.
- **Conservative cross-ID mapping** — runtime mapping is direct-only and conflict-aware, with provenance and manual audited overrides.
- **Aggregated metadata cards** — values from successful metadata sources are normalized and merged while source-specific provenance is preserved.
- **Lazy heavy sections** — people, portraits, characters, trailers, and episodes are fetched on demand.
- **Shared resilience layer** — typed source errors, retries, circuit breakers, half-open recovery, rate limits, and shared HTTP lifecycle.
- **Persistent platform-scoped settings** — user locale, known users, and moderation state are stored in SQLite.
- **Three UI languages** — English is the default/fallback locale; Russian and Japanese are fully selectable in `/settings`.
- **Production-oriented checks** — Python 3.11–3.14 CI + experimental 3.15 probe, Ruff, formatter checks, mypy scope, coverage gate, and ShellCheck.

## Source capabilities

| Source | Search | Metadata | People | Characters | Trailers | Episodes |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ |

AniDB is optional and is enabled only when `ANIDB_CLIENT` is configured. Jikan is **not** a separate identity database: it is a local MAL backend used for data that is not available through the official MAL API.

## How it works

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

### Identity rules

`AnimeIdentity` has no primary ID. A numeric ID from one database is never assumed to identify the same title in another database simply because the number matches.

Cross-source merging follows conservative rules:

1. explicit shared external IDs are strong identity evidence;
2. conflicting IDs from the same provider prevent a merge;
3. text search may use a constrained exact normalized romaji fallback only when no same-provider conflict exists;
4. direct-ID lookup does **not** use title-only merging;
5. runtime mappings are direct-only and do not recursively traverse arbitrary TVDB/TMDB-style chains.

The full enriched identity remains available internally for routing and lazy capabilities. The card's visible ID block shows only IDs belonging to metadata sources that actually contributed to that card.

## Search

The only user-facing search command is `/anime`.

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
```

`/anime <title>` queries all registered search providers in parallel and collects a bounded query-scoped result set before Telegram pagination. Relevance considers titles, aliases, native/romaji variants, token/prefix matches, transliteration, and a conservative similarity fallback.

Hard page/item caps protect upstream quotas. When the bot cannot prove that the collected count is final, the UI reports an incomplete count instead of presenting it as exact.

Running `/anime` without arguments opens an interactive source selector. Pending input is scoped to the user/chat pair, expires automatically, and can be cancelled with `/cancel`.

## Lazy card sections

The main card stays metadata-first. The following sections are loaded only when requested:

- staff and creators;
- original Japanese voice actors;
- characters and portraits;
- trailers/promos;
- episodes.

Foreign dub credits are not mixed into the original Japanese voice list. Localization/ADR staff is excluded from the primary production staff list.

## Requirements

Recommended environment:

- Linux server;
- Python **3.11, 3.12, 3.13, or 3.14**;
- Git;
- `tmux` for the bundled `start.sh` runtime;
- Docker + Docker Compose for the optional local Jikan supplement.

The application can still run without Docker; MAL remains available through its official API, while Jikan-only supplemental features are disabled.

## Quick start

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot

cp .env.example .env
# Edit .env and add at least BOT_TOKEN.

./scripts/setup.sh
./scripts/check.sh
./start.sh
```

`start.sh` starts the Telegram bot in a detached `tmux` session and attempts to start the local Jikan container when Docker Compose is available.

Useful runtime commands:

```bash
tmux attach -t anime-db-bot
tail -f logs/bot.log
```

## Configuration

All runtime environment parsing is centralized in `core/settings.py`. Start from `.env.example`; it documents every supported setting and safe default.

### Essential settings

| Variable | Required | Purpose |
| --- | :---: | --- |
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather. |
| `MAL_CLIENT_ID` | Recommended | Enables official MyAnimeList search and metadata. |
| `ANIDB_CLIENT` | No | Enables AniDB HTTP API metadata/people/episodes. |
| `ANIDB_CLIENT_VERSION` | No | Registered AniDB HTTP API client version; defaults to `1`. |
| `ANILIST_ACCESS_TOKEN` | No | Optional AniList token when authenticated access is desired. |
| `ADMIN_TELEGRAM_USER_IDS` | No | Comma/space/semicolon-separated Telegram admin user IDs. |
| `TELEGRAM_BOT_API_URL` | No | Custom/self-hosted Telegram Bot API endpoint. |
| `USER_SETTINGS_DB_PATH` | No | SQLite path for per-user settings and known-user registry. |
| `BANS_DB_PATH` | No | SQLite path for moderation bans. |
| `MAPPINGS_DB_PATH` | No | Runtime cross-ID mapping database. |

Do not commit `.env`, bot tokens, access tokens, passwords, or private API credentials.

### AniDB

The integration uses the AniDB HTTP API. It requires a registered HTTP API **client name and version**, not an AniDB account password.

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

AniDB XML responses are cached on disk and network requests are serialized with an additional minimum request interval to respect the service's API expectations.

### MAL / Jikan

MAL is the identity source. Jikan is a local supplemental backend and never introduces a `jikan` identity key.

The bundled service lives under:

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

A Jikan outage does not make official MAL search/metadata unavailable.

## Commands

### User commands

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

### Admin commands

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

Mapping mutations are intentionally two-step. `/mapping_set` and `/mapping_delete` create a short-lived pending mutation; the database changes only after `/mapping_confirm <token>`. Audit history records the Telegram administrator responsible for the change.

## Localization

The domain model is locale-neutral. Source adapters normalize upstream status/type/season/genre/role values into canonical keys, and translation happens only at render time.

Supported UI locales:

- `en` — English (**default and fallback**);
- `ru` — Русский;
- `ja` — 日本語.

Existing users keep their explicitly saved locale. New users, missing settings, invalid locale values, and missing translation keys fall back to English.

Free-form source text such as anime descriptions is not machine-translated. See [`localization/README.md`](localization/README.md) for localization architecture and maintenance rules.

## Persistence

The runtime keeps different kinds of state separate:

- user settings and known users — SQLite, scoped by `(platform, user_id)`;
- bans — separate persistent SQLite store;
- `mappings.db` — disk-backed cross-ID resolver database;
- AniDB XML — disk cache;
- Telegram search/card callback sessions — bounded in-memory TTL/LRU state.

Legacy user settings created before platform scoping are migrated as Telegram records without changing their saved locale.

## Resilience and rate limiting

Outbound HTTP uses shared `httpx.AsyncClient` instances owned by `AppContext`. Source failures are normalized into typed errors and passed through a common retry/circuit-breaker layer.

The source health registry supports:

- transient vs. non-transient failure handling;
- bounded retries with backoff;
- circuit breaker thresholds;
- cooldowns;
- exactly one half-open recovery probe.

Personal Telegram limits are scoped per `(platform, user_id)`. Administrators may bypass the personal limiter, but **never** bypass upstream provider safety limits.

## Architecture

```text
anime-db-bot/
├── bots/telegram/
│   ├── card/            # card runtime, feature handlers, UI primitives and views
│   │   ├── features/    # characters, episodes, screenshots, trailers
│   │   ├── runtime/     # handlers, session state and card service wiring
│   │   ├── ui/          # callbacks-facing keyboards, selectors and constants
│   │   └── views/       # renderers and section presentation
│   ├── people/          # lazy people loading, portraits and views
│   ├── search/          # Telegram search handlers/UI
│   └── transports/      # official and self-hosted Bot API transports
├── core/                # contracts, models, identity, settings, HTTP, errors
├── localization/        # locale catalogs and canonical localization data
├── mappings/            # cross-ID database, importers, resolver, updater
├── search/              # provider-facing search adapters and registry
├── services/
│   ├── aggregation/     # metadata aggregation and merge policy
│   ├── identity/        # direct lookup and cross-source identity resolution
│   ├── media/           # characters, episodes, people and trailers
│   ├── runtime/         # AppContext, source health and rate-limit runtime policy
│   ├── search/          # search orchestration and query expansion
│   └── users/           # access control, bans and persistent user settings
├── sources/
│   ├── providers/       # MAL, AniList, Shikimori, AniDB and Jikan adapters
│   └── runtime/         # source catalog, registries and resilience wrappers
├── tests/               # unit, integration, wiring and regression tests
├── jikan_service/       # local Jikan/MAL supplement service
├── scripts/             # setup, checks and maintenance helpers
└── deploy/systemd/      # optional maintenance units
```

`services/runtime/app_context.py` is the application composition root. Production runtime dependencies should be owned there rather than created as import-time service singletons.

More detail: [`docs/app-context.md`](docs/app-context.md).

## Cross-ID mappings

The mapping updater streams several external datasets into SQLite, records provenance/evidence/conflicts, validates the rebuilt database, and atomically swaps it into place. The complete graph is not loaded into RAM.

Manual directional overrides support `accept` and `reject`, carry author/reason/timestamp metadata, and preserve append-only history across rebuilds.

Maintenance commands:

```bash
./scripts/update-mappings.sh
.venv/bin/python -m mappings --status
.venv/bin/python -m mappings --override-list
.venv/bin/python -m mappings --override-history
```

## Development

Set up the locked environment:

```bash
./scripts/setup.sh
```

Run the normal local checks:

```bash
./scripts/check.sh
```

Useful direct commands:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bots core localization mappings search services sources tests
.venv/bin/python -m pip check
```

GitHub Actions requires Python 3.11, 3.12, 3.13, and 3.14 to pass; Python 3.15 runs as an experimental compatibility probe until the aiogram dependency supports it. The quality job additionally runs Ruff correctness checks, formatter checks for the typed foundation, mypy for the typed foundation, full tests with a coverage gate of at least 70%, and ShellCheck for shell scripts.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request and follow the project [Code of Conduct](CODE_OF_CONDUCT.md). Bug reports and feature requests should use the repository issue forms.

## Security

- Keep `.env` and credentials outside version control.
- Logs use secret redaction, per-update correlation IDs, privacy-safe structured source/cache/health/resolver events, and bounded file rotation; avoid adding raw credentials or user/query identifiers to custom log messages.
- Admin-only actions must remain behind the access-control layer.
- Do not expose a self-hosted Telegram Bot API, future metrics endpoint, or future external API publicly without explicit authentication/network controls.
- Mapping overrides are audited because an incorrect identity edge can affect multiple capabilities.

For vulnerability reporting and supported security channels, see [SECURITY.md](SECURITY.md). Do not publish credentials, tokens, or private deployment details in a public issue.

## Project status

The project is under active development. The core Telegram search/card flow, identity model, mapping database, multi-source aggregation, localization, lazy capabilities, persistence, resilience, and CI foundation are implemented. Additional discovery/search filters, user account integrations, notifications, monitoring/Prometheus metrics, external API/Mini App support, and more sources are planned work.

## License

Licensed under the [Apache License 2.0](LICENSE). You may use, modify, and distribute the project under its terms; preserve the required notices and mark significant modifications as required by the license.

## Data sources and acknowledgements

`anime-db-bot` integrates with or builds on data from projects and services including:

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)

Cross-ID mapping data is assembled from multiple community datasets. Each upstream service and dataset remains subject to its own terms, rate limits, and attribution requirements.
