> **AI-assisted project:** This project was developed with the help of AI.

<p align="center">
  <strong>English</strong> · <a href="docs/README.ru.md">Русский</a> · <a href="docs/README.ja.md">日本語</a>
</p>

# anime-db-bot

> Identity-native Telegram anime search and metadata aggregation across MyAnimeList/Jikan, AniList, Shikimori, Kitsu, AniDB, and AniSearch.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](LICENSE)

`anime-db-bot` searches multiple anime databases, resolves confirmed cross-database identities, and builds one source-independent card without treating any external database as the canonical source of truth.

The project is designed around explicit boundaries between **search**, **identity**, **mappings**, **metadata sources**, **aggregation**, **localization**, and **platform UI**. People use a prefetched lightweight ID/name/role manifest for exact totals, while portraits are enriched in bounded global batches; other expensive data such as characters, trailers, and episodes stays lazy.

## Highlights

- **Multi-provider search** — Shikimori, MyAnimeList, AniList, and Kitsu are queried through one `/anime` flow.
- **Source-independent identity** — `AnimeIdentity` stores peer external IDs; there is no global primary database ID.
- **Conservative cross-ID mapping** — runtime mapping is direct-only and conflict-aware, with provenance and manual audited overrides.
- **Aggregated metadata cards** — values from successful metadata sources are normalized and merged while source-specific provenance is preserved.
- **Manifest + lazy enrichment** — staff/seiyuu IDs, names, and roles are prefetched as a lightweight exact roster; portraits are enriched in global batches (50 by default), while characters, screenshots, detailed popularity, descriptions/backgrounds, trailers, and episodes remain lazy.
- **Shared resilience layer** — typed source errors, retries, circuit breakers, half-open recovery, rate limits, and shared HTTP lifecycle.
- **Persistent platform-scoped settings** — user locale, known users, and moderation state are stored in SQLite.
- **Three UI languages** — English is the default/fallback locale; Russian and Japanese are fully selectable in `/settings`.
- **Production-oriented checks** — Python 3.11–3.14 CI, Ruff, formatter checks, mypy scope, coverage gate, and ShellCheck.

## Source capabilities

| Source | Search | Metadata | People | Characters | Trailers | Episodes | Screenshots | Popularity | Description |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu is an identity-native public JSON:API source. Public read-only GET requests do not require OAuth credentials; confirmed Kitsu IDs already participate in `mappings.db`, and Kitsu can also return direct MAL/AniList/AniDB mappings with search results and metadata. Kitsu currently contributes search, metadata, popularity, descriptions, episodes, and a YouTube trailer when available. People/characters are intentionally not advertised because those relationships are often sparse.

AniDB is optional and is enabled only when `ANIDB_CLIENT` is configured. Jikan is **not** a separate identity database: it is a local MAL backend used for data that is not available through the official MAL API. Its main-card licensors and lazy popularity statistics use separate local endpoints, so score-distribution scraping is not on the initial card path. AniSearch is an identity-native Database API source resolved through confirmed `anisearch` mapping edges. Its public API does not expose normal title-query search, so it does not join the fast `/anime <title>` search path. Because AniSearch puts ID and `/full` in the same strict throttle group, the source performs one cached `/full` fetch per title and keeps heavy fields out of initial aggregation; people, characters, and episodes later reuse that same payload without another network wait. Only English and Japanese localized AniSearch data is consumed for now. Public no-token requests are paced to the documented 10-second ID-family interval (5 seconds with a valid token), and AniSearch-sourced synopsis text keeps the required direct AniSearch attribution link. SkipDB support remains in the codebase as a dormant IMDb-backed provider, but it is intentionally not registered in the runtime because current anime skip-segment coverage is too small to justify exposing it in the UI. Its parser/settings/tests are kept so it can be re-enabled later if coverage improves. SkipDB data is served under ODbL 1.0 + reciprocity.

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
/anime kitsu:<id>
```

`/anime <title>` queries all registered search providers in parallel and collects a bounded query-scoped result set before Telegram pagination. Relevance considers titles, aliases, native/romaji variants, token/prefix matches, transliteration, and a conservative similarity fallback.

Hard page/item caps protect upstream quotas. When the bot cannot prove that the collected count is final, the UI reports an incomplete count instead of presenting it as exact.

Running `/anime` without arguments opens an interactive source selector. Pending input is scoped to the user/chat pair, expires automatically, and can be cancelled with `/cancel`.

`/anime` also supports reverse image search. Attach an image to the command or pass a public image URL and the bot offers only image-search backends whose quota is currently available: trace.moe, What Anime Is This, or both. Results are resolved through confirmed AniList IDs and shown as the normal paginated candidate preview; the full metadata card is opened only after the user chooses **Details**. Matching evidence (provider, similarity, episode, timestamp) is kept on the preview. The **Not the title you need?** action allows another source attempt or cancellation without bypassing provider quotas. Uploaded raster images are normalized to JPEG before outbound search.

Image-search credentials are optional. trace.moe runs anonymously when `TRACE_MOE_API_KEY` is empty and reads the real current quota from `/me`; configured keys are sent as `x-trace-key`, so partner/donor quotas are discovered rather than hard-coded. What Anime Is This runs as a guest when `WHATANIMEISTHIS_API_KEY` is empty and uses `Authorization: Bearer ...` when a key is present. Because its public API does not expose API-key credit state, the bot maintains a conservative persistent local daily counter: defaults are 5 guest searches and 10 API-key searches, and both ceilings are configurable for accounts with different credit policies. Set `WHATANIMEISTHIS_API_DAILY_LIMIT=0` to disable the local API-key ceiling and rely on the service's own credit/quota errors. A server-side quota response immediately marks that backend unavailable for the current local quota period.

## Lazy card sections

The main card stays metadata-first. The following sections are loaded only when requested:

- staff and creators;
- original Japanese voice actors;
- characters and portraits;
- screenshots;
- detailed popularity/ranking distributions;
- descriptions and source background text;
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

cp -R .env.example.d .env.d
cp -R .proxies.example.d .proxies.d
cp -R .user-agents.example.d .user-agents.d
# Edit .env.d/telegram.env and add at least BOT_TOKEN.
# Proxy files are optional; their example entries are disabled/commented by default.

./scripts/setup.sh
./scripts/check.sh
./start.sh
```

`start.sh` starts the Telegram bot in a detached `tmux` session and attempts to start the local Jikan container when Docker Compose is available.

Useful runtime commands:

```bash
tmux attach -t anime-db-bot
TODAY="$(date '+%Y.%m.%d')"
tail -f "logs/$TODAY/bot.log"
tail -f "logs/$TODAY/users.log"
tail -f "logs/$TODAY/api.log"
```

Runtime logs are split by responsibility under `logs/YYYY.MM.DD/`: `bot.log` contains application/runtime events, `users.log` contains Telegram user-action tracing, `api.log` contains outbound source/API/retry/health events, and `errors.log` duplicates all `ERROR+` records for quick diagnostics. The directory switches automatically after local midnight without restarting the bot.

## Configuration

All runtime environment parsing is centralized in `core/settings.py`. New deployments copy `.env.example.d/` to `.env.d/`. Only the fixed files `telegram.env`, `sources.env`, `timestamps.env`, `rate-limits.env`, `mappings.env`, `storage.env`, `logging.env`, and `runtime.env` are loaded; stray files such as `backup.env` are ignored. Duplicate keys across project config files fail startup, while real process environment variables have the highest priority. A monolithic `.env` remains supported only as a migration path.

### Essential settings

| Variable | Required | Purpose |
| --- | :---: | --- |
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather. |
| `MAL_CLIENT_ID` | Recommended | Enables official MyAnimeList search and metadata. |
| `ANIDB_CLIENT` | No | Enables AniDB HTTP API metadata/people/episodes. |
| `ANIDB_CLIENT_VERSION` | No | Registered AniDB HTTP API client version; defaults to `1`. |
| `ANILIST_ACCESS_TOKEN` | No | Optional AniList token when authenticated access is desired. |
| `KITSU_API_URL` | No | Kitsu public JSON:API base URL; defaults to `https://kitsu.io/api/edge`. |
| `TRACE_MOE_API_KEY` | No | Optional trace.moe API key (`x-trace-key`); free mode works without it and quota is read from `/me`. |
| `WHATANIMEISTHIS_API_KEY` | No | Optional What Anime Is This API key sent as `Authorization: Bearer ...`; free guest mode works without it. |
| `IMAGE_SEARCH_DB_PATH` | No | SQLite path for conservative persistent image-search quota accounting. |
| `ADMIN_TELEGRAM_USER_IDS` | No | Comma/space/semicolon-separated Telegram admin user IDs. |
| `TELEGRAM_BOT_API_URL` | No | Custom/self-hosted Telegram Bot API endpoint. |
| `USER_SETTINGS_DB_PATH` | No | SQLite path for per-user settings and known-user registry. |
| `BANS_DB_PATH` | No | SQLite path for moderation bans. |
| `MAPPINGS_DB_PATH` | No | Runtime cross-ID mapping database. |

Do not commit `.env`, `.env.d/`, `.proxies.d/`, bot tokens, access tokens, passwords, proxy credentials, or private API credentials.

### Per-source proxy pools

Optional outbound proxy routing is configured separately under `.proxies.d/`, one fixed TOML file per runtime source plus `telegram.toml` for the bot itself. Start from `.proxies.example.d/`. Supported proxy schemes are `http`, `socks4`, and `socks5`.

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

Profiles are independent: `mal.toml` affects only MAL, `anilist.toml` only AniList, and so on. Higher `priority` values are tried before lower values regardless of TOML order. Entries tied at the same priority are round-robin selected; lower-priority tiers are used only as failover after the higher tier fails. Duplicate proxy URLs are allowed when they have distinct entry names, so repeating an endpoint can intentionally give it more rotation weight. `enabled = false` can disable either the whole profile or an individual entry. If at least one proxy entry is active for a profile, that profile does **not** silently fall back to the direct connection when all proxies fail; direct access is used only when the profile has no active proxies. Proxy configuration is loaded at process startup, so edits take effect after a bot restart. When `telegram.toml` has active proxies, this bot intentionally bypasses any configured local/shared `telegram-bot-api` endpoint and talks to the official `api.telegram.org` through its own proxy pool; this keeps the proxy scoped to this bot instead of changing other bots that share the local server. `jikan.toml` is also special: the Python hop to the loopback Jikan service stays direct, while the selected proxy is forwarded to the local Jikan service and applied to its outbound MyAnimeList scrape.

Fixed runtime profiles are: `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `bahamut`, `baha_anime_skip`, `skipdb`, `trace_moe`, and `whatanimeisthis`. Stray TOML files are ignored. Proxy files may contain credentials and are gitignored; `start.sh` keeps `.proxies.d` at mode `700` and known profile files at mode `600`.

### Per-source User-Agent profiles

Optional User-Agent overrides live under `.user-agents.d/` with the same fixed profile names as proxy routing. If a profile has no active custom entry, requests use the built-in project User-Agent (`anime-db-bot/<version> (...)`). Higher `priority` wins; entries tied at the highest active priority rotate between requests. Lower-priority User-Agents remain standby until higher-priority entries are disabled.

```toml
enabled = true

[[user_agent]]
name = "browser-a"
enabled = true
priority = 100
value = "Mozilla/5.0 custom-a"

[[user_agent]]
name = "browser-b"
enabled = true
priority = 100
value = "Mozilla/5.0 custom-b"

[[user_agent]]
name = "backup"
enabled = true
priority = 10
value = "anime-db-bot-backup/1.0"
```

The network boundary overrides provider-local `User-Agent` headers so the selected profile value is authoritative. For `jikan`, the selected User-Agent is forwarded through the loopback service and applied to its outbound MyAnimeList request. For `telegram`, an active custom User-Agent switches this bot from a shared/local `telegram-bot-api` endpoint to the official `api.telegram.org`, ensuring that the configured header reaches the external Telegram request. `.user-agents.d` is gitignored and loaded at process startup.

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
/anime kitsu:<id>
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
│   │   ├── features/    # characters, descriptions, episodes, popularity, screenshots, trailers
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
│   ├── providers/       # MAL, AniList, Shikimori, Kitsu, AniDB, AniSearch and Jikan adapters
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

GitHub Actions requires Python 3.11, 3.12, 3.13, and 3.14 to pass. The quality job additionally runs Ruff correctness checks, formatter checks for the typed foundation, mypy for the typed foundation, full tests with a coverage gate of at least 70%, and ShellCheck for shell scripts.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request and follow the project [Code of Conduct](CODE_OF_CONDUCT.md). Bug reports and feature requests should use the repository issue forms.

## Security

- Keep `.env` and credentials outside version control.
- Logs use daily `bot/users/api/errors` files, secret redaction by default, per-update correlation IDs, runtime-local timezone timestamps, and bounded per-file rotation. `LOG_REDACT_SECRETS=0` deliberately disables all masking for local diagnostics and may write credentials verbatim; keep it enabled on shared/public logs.
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
- [Kitsu](https://kitsu.app/) — public read-only JSON:API; no OAuth required for normal GET requests
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) — Database API metadata; attribution and synopsis-link requirements apply
- [SkipDB](https://skipdb.tv/) — skip-segment data under ODbL 1.0 + reciprocity

Cross-ID mapping data is assembled from multiple community datasets. Each upstream service and dataset remains subject to its own terms, rate limits, and attribution requirements.

Kitsu public read-only GET requests are used without OAuth credentials. The runtime applies its own conservative request limits because no stable server-side rate-limit contract is assumed.

AniSearch Database API read-only metadata requests do not require OAuth. `ANISEARCH_APP_ID` and `ANISEARCH_APP_SECRET` are optional OAuth application credentials reserved for future user-authorized AniSearch features; they are never sent with read-only database requests.
