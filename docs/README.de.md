> **KI-unterstütztes Projekt:** Dieses Projekt wurde mit Hilfe von KI entwickelt.

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <strong>Deutsch</strong> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

Ein Telegram-Bot, der Anime über unabhängige Datenbanken hinweg sucht und Informationen zu Titeln, Folgen, Figuren, Mitwirkenden und verwandten Werken in einer Oberfläche zusammenführt.

## Funktionen

- Suche nach Titel, externer ID oder Bild mit seitenweiser Ergebnisanzeige.
- Aggregierte Bewertungen, Beschreibungen, Ausstrahlungsdaten, Besetzungen, Mitwirkende und Empfehlungen.
- Folgen, OP-/ED-Informationen und verfügbare Skip-Zeitbereiche werden bei Bedarf geladen.
- Titel werden nur über bestätigte ID-Zuordnungen zusammengeführt.
- Gespeicherte Einstellungen, Moderation, quellenspezifische Limits sowie Proxy- und User-Agent-Profile.
- Benutzeroberfläche in sieben Sprachen; Quelltexte bleiben in den verfügbaren Originalsprachen.

## Datenquellen

Für Anime-Metadaten dienen MyAnimeList (Jikan ergänzend), AniList, Shikimori, Kitsu, AniDB (optionale Client-Registrierung) und AniSearch. Weitere Dienste unterstützen gezielte Zusatzfunktionen.

| Funktionen | Datenquellen |
| --- | --- |
| Suche und Metadaten | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Zusätzliche Bewertungen | [IMDb](https://www.imdb.com/) |
| Bilderkennung | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Folgen, Themes und Skip-Intervalle | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) liefert die dienstübergreifenden ID-Zuordnungen. Der SkipDB-Zeitstempelanbieter ist derzeit deaktiviert; die Quellenliste garantiert keine Abdeckung aller Titel oder Folgen.

## Schnellstart

Voraussetzungen: Python 3.11–3.14 sowie Linux, macOS oder Windows. Repository klonen und den plattformübergreifenden Launcher verwenden:

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# BOT_TOKEN in .env.d/telegram.env eintragen
python3 scripts/project.py check
python3 scripts/project.py run
```

Unter Windows `py -3 scripts\project.py` statt `python3 scripts/project.py` verwenden. Der Hintergrundbetrieb erfolgt mit `python3 scripts/project.py start` (auch `status`, `restart`, `stop`); unter Linux steht `./start.sh` bereit.

## Verwendung

Mit `/anime` lässt sich eine Suchquelle wählen oder ein Titel suchen. Ein an `/anime` angehängtes Bild oder eine öffentliche Bild-URL startet bei verfügbarem Dienst die Rückwärtssuche. `/settings` ändert Einstellungen, `/cancel` beendet die Eingabe.

```text
/anime Frieren
/anime mal:5114
/anime anilist:<id>
/anime shikimori:<id>
/settings
/ping
/cancel
```

## Konfiguration

`BOT_TOKEN` ist erforderlich. Zugangsdaten anderer Dienste sind optional: `MAL_CLIENT_ID` erweitert die MAL-Funktionen, `ANIDB_CLIENT` aktiviert AniDB. Bildsuche ist auch als Gast möglich. Proxys und User-Agents werden in `.proxies.d/` und `.user-agents.d/` konfiguriert.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Der Bot lädt geprüfte Releases von **Anime Mapping DB** und liest `mappings.db` direkt. Er baut keine Mapping-Datenbank und benötigt **Anime Timestamp DB** nicht.

## Dokumentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Lizenz und Quellenangaben

Der Code steht unter Apache-2.0. Für Drittanbieter-Daten gelten deren Lizenzen, Quellenpflichten und API-Bedingungen. Zugangsdaten dürfen nicht eingecheckt werden. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
