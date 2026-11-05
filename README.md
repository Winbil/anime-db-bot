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

## Data sources

The bot uses MyAnimeList (with Jikan as an optional supplement), AniList, Shikimori, Kitsu, AniDB (optional client registration), and AniSearch for anime metadata. Additional services serve narrowly scoped features rather than acting as interchangeable metadata databases.

| Features | Data sources |
| --- | --- |
| Anime metadata and search | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Additional ratings | [IMDb](https://www.imdb.com/) |
| Image recognition | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Episodes, themes and skip intervals | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) provides cross-database ID mappings. SkipDB's timestamp provider is present but currently dormant; a source listed here does not imply that all titles or episodes have data.

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

## Configuration

`BOT_TOKEN` is required. Add provider credentials only for the services you intend to enable; `MAL_CLIENT_ID` improves MyAnimeList coverage and `ANIDB_CLIENT` enables AniDB. Optional reverse-image API keys are not required for guest operation. Proxy and User-Agent profiles are configured under `.proxies.d/` and `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

The bot downloads and verifies release artifacts from **Anime Mapping DB**. It consumes `mappings.db` directly and does not build mapping datasets or automatically incorporate **Anime Timestamp DB**.

## Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [Application architecture](docs/app-context.md) · [Localization](localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## License and attribution

Source code is available under Apache-2.0. Third-party services and datasets retain their own licenses, attribution requirements, and API terms. Keep credentials outside version control. [Apache-2.0](LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
