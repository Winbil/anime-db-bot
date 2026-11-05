> **AI-assisted project:** Developed with the assistance of AI.

<p align="center">
  <strong>English</strong> · <a href="docs/README.ru.md">Русский</a> · <a href="docs/README.ja.md">日本語</a> · <a href="docs/README.de.md">Deutsch</a> · <a href="docs/README.es.md">Español</a> · <a href="docs/README.fr.md">Français</a> · <a href="docs/README.it.md">Italiano</a>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](LICENSE)

A Telegram bot for searching anime, combining metadata from independent databases, and exploring titles, episodes, characters, staff, and related works in one interface.

## Features

- Search anime by title, external ID, or image, with interactive result pagination.
- Combine ratings, descriptions, release information, cast, staff, relations and recommendations from multiple providers.
- Browse episodes, OP/ED information and available skip timestamps; expensive sections load only when opened.
- Keep cross-database identity conservative: only verified ID relationships may merge titles.
- Use persistent user preferences, moderation tools, per-source rate limits, proxies, and User-Agent profiles.
- Choose among seven interface languages; source text is displayed in the languages upstream provides.

## Search and navigation

The `/anime` workflow accepts a title or an explicit provider ID. Search candidates are paginated before a detailed card is opened. Results use names and aliases from different writing systems, but exact external-ID lookups never rely on a title-only match.

Image recognition accepts a Telegram image or public image URL. Available providers show similarity, episode and timestamp evidence before the user opens an anime card; guest quotas and API-key quotas are handled per provider.

The main card presents normalized title information. More expensive sections—characters, staff, voice cast, screenshots, detailed ratings, descriptions, trailers, related titles, recommendations, and episodes—are loaded on demand. Episode views can include seasons/cours/specials when the underlying source provides that structure.

## Data sources

The bot uses MyAnimeList (with Jikan as an optional supplement), AniList, Shikimori, Kitsu, AniDB (optional client registration), and AniSearch for anime metadata. Additional services serve narrowly scoped features rather than acting as interchangeable metadata databases.

| Features | Data sources |
| --- | --- |
| Anime metadata and search | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Additional ratings | [IMDb](https://www.imdb.com/) |
| Image recognition | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Episodes, themes and skip intervals | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) provides cross-database ID mappings. SkipDB's timestamp provider is present but currently dormant; a source listed here does not imply that all titles or episodes have data.

## Provider capabilities

| Source | Title search | Metadata | People | Characters | Episodes | Relations | Recommendations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch enriches confirmed titles with localized metadata and voice credits but does not participate in ordinary title search. AnimeThemes enriches episodes with OP/ED metadata rather than creating anime identities. SkipDB remains an inactive runtime timestamp provider, not a promise of skip coverage.

## Identity and data aggregation

The project does not assign authority to a single anime catalog. MAL, AniList, Shikimori, Kitsu, AniDB and AniSearch identities remain distinct until confirmed mappings associate them. A matching number, similar title or franchise membership is not sufficient proof.

Runtime mapping is direct-only and conflict-aware. Aggregation retains attribution to each responding service; provider-specific views remain available where implemented. IMDb ratings require a direct, unambiguous anime-native mapping; TVDB/TMDB bridge matches alone cannot identify the correct IMDb title.

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

## Quick start

Python 3.11–3.14 on Linux, macOS or Windows. Clone the project and use its cross-platform launcher:

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# Add BOT_TOKEN to .env.d/telegram.env
python3 scripts/project.py check
python3 scripts/project.py run
```

Windows: use `py -3 scripts\project.py` instead of `python3 scripts/project.py`. Background operation uses `python3 scripts/project.py start` (`status`, `restart`, `stop` are also supported); Linux deployments may use `./start.sh`.

## Deployment and operation

The cross-platform launcher manages virtual environments, checks, foreground/background execution and process status. For Linux, `start.sh` provides the existing tmux-based deployment path. Windows has `start.ps1`/`start.cmd`; macOS also includes `start.command`.

Docker Compose and local Jikan are optional supplements. The official MAL integration can operate without Jikan. Linux `systemd` templates are available under `deploy/systemd/` for maintenance; they are not required on Windows or macOS.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

## Usage

Use `/anime` to choose a search source or enter a title. An image attached to `/anime` or a public image URL activates image search when a backend is available. `/settings` changes preferences; `/cancel` ends pending input.

```text
/anime Frieren
/anime mal:5114
/anime anilist:<id>
/anime shikimori:<id>
/settings
/ping
/cancel
```

## Telegram commands

The interactive `/anime` command is the entry point for ordinary searches. Administrative commands require configured Telegram administrator IDs and enforce access control. Mapping changes have a confirmation step and are recorded in an audit history.

| Command | Purpose |
| --- | --- |
| `/start`, `/ping` | Start/help and basic health check |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | Search by title, numeric ID, provider ID or image |
| `/settings` | User language and preferences |
| `/cancel` | Cancel pending interactive input |
| `/users`, `/status`, `/source_health` | List known users; runtime statistics and provider health |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | Ban or unban a Telegram user |
| `/mapping_overrides`, `/mapping_history [limit]` | Inspect overrides and mapping audit history |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | Stage mapping decisions, then confirm or cancel |

## Configuration

`BOT_TOKEN` is required. Add provider credentials only for the services you intend to enable; `MAL_CLIENT_ID` improves MyAnimeList coverage and `ANIDB_CLIENT` enables AniDB. Optional reverse-image API keys are not required for guest operation. Proxy and User-Agent profiles are configured under `.proxies.d/` and `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

The bot downloads and verifies release artifacts from **Anime Mapping DB**. It consumes `mappings.db` directly and does not build mapping datasets or automatically incorporate **Anime Timestamp DB**.

## Configuration reference

Configuration templates are copied into `.env.d/` without overwriting existing settings. Only the predefined env filenames are loaded. Process environment values take precedence; duplicate project-file keys cause startup failure. Keep credentials and private profiles out of Git.

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token (required) |
| `MAL_CLIENT_ID` | Official MyAnimeList API client ID |
| `ANIDB_CLIENT` | Optional AniDB HTTP API client name |
| `ANILIST_ACCESS_TOKEN` | Optional authenticated AniList access |
| `TRACE_MOE_API_KEY` | Optional trace.moe key; guest mode exists |
| `WHATANIMEISTHIS_API_KEY` | Optional What Anime Is This key; guest mode exists |
| `ADMIN_TELEGRAM_USER_IDS` | Telegram IDs permitted to run admin commands |
| `TELEGRAM_BOT_API_URL` | Custom Telegram Bot API endpoint |
| `MAPPINGS_DB_PATH` | Runtime cross-ID mapping database path |
| `IMDB_RATINGS_BACKEND` | IMDb local/API/off selection |
| `BAHA_ANIME_SKIP_DB_PATH` | Local Baha Anime Skip index path |

Each source can have an independent TOML proxy profile in `.proxies.d/`. Supported protocols include HTTP, SOCKS4 and SOCKS5. Higher priorities win, equal-priority entries rotate and lower priorities are fallbacks; an active proxy profile does not silently bypass failed proxies using direct access.

Custom User-Agent profiles live in `.user-agents.d/` and support prioritization. Both types of profile are loaded when the process starts, so restart after editing. Self-hosted Telegram Bot API endpoints are optional and must be secured.

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

The reference templates under `.env.example.d/`, `.proxies.example.d/`, and `.user-agents.example.d/` define available settings and profile filenames.

## Local data and maintenance

The mapping updater downloads a versioned `mappings.db.zst`, verifies checksums and replaces the local database atomically while preserving audited overrides. The bot reads the compact runtime database; it never downloads the mapping evidence DB for normal operation.

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

The optional local IMDb index keeps only ratings tied to accepted anime-native identifiers, rather than storing the full IMDb ratings dump. Baha Anime Skip timestamps are indexed locally and queried without live Bahamut requests. Both indexes can be refreshed independently after the mapping database is available.

User preferences, known-user data, moderation state and certain local quotas are persisted in SQLite. Daily logs are grouped under `logs/YYYY.MM.DD/` as `bot.log`, `users.log`, `api.log` and `errors.log`. The background launcher also writes `logs/launcher.log`.

## Episode data, OP/ED and skip intervals

Episode listings and skip timestamps are separate capabilities. The selected episode-list provider does not determine which timestamp service can be used: each provider keeps its own source IDs and scope. When no trusted match exists, the bot should display the absence of data rather than borrow an unrelated episode.

AnimeThemes adds opening/ending names, songs, artists and available video links to the relevant episode view. Timestamp services can identify intervals such as OP, ED and recap; their reported ranges may differ because source numbering and video editions differ. A label describing one source does not mean all sources confirm that interval.

## Operations and diagnostics

Before troubleshooting a missing title, confirm which source responded and whether the cross-ID mapping exists. An API timeout or missing optional key should affect its own provider, not the entire search flow. Use `/status` for rolling runtime statistics and `/source_health` for circuit-breaker state.

If the process does not start, run `doctor` and `check`, inspect `logs/YYYY.MM.DD/errors.log` and ensure `BOT_TOKEN` is set. Changes in `.env.d/`, proxy or User-Agent profiles require a restart. Check the mapping manifest and updater status before rebuilding optional IMDb/Baha indexes.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## Architecture and reliability

Search, identity resolution, source clients, aggregation, localization, persistence and Telegram presentation are separated. Source-level timeouts, retry policies, rate limits and circuit breakers reduce the impact of individual provider failures.

```text
bots/telegram/    Telegram UI, card and search handlers
core/             contracts, settings, HTTP and logging
search/           search source adapters
services/         identity, aggregation, runtime and media
sources/          API providers and source health
mappings/         local cross-ID resolution and updater
localization/     seven UI locale catalogs
jikan_service/    optional local MAL supplement
deploy/systemd/   optional Linux service/timer units
tests/            automated regression tests
```

## Development and security

Contributions should preserve conservative identity matching and avoid adding network calls to the initial card without justification. Use the supported Python versions and run the project checks before opening a pull request. Report vulnerabilities privately through the security guidance; never post tokens in issues.

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md)

## Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [Application architecture](docs/app-context.md) · [Localization](localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## License and attribution

Source code is available under Apache-2.0. Third-party services and datasets retain their own licenses, attribution requirements, and API terms. Keep credentials outside version control. [Apache-2.0](LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
