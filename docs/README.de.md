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

## Das Ökosystem in Zahlen

Der Bot ist Teil einer Familie unabhängig nutzbarer Anime-Datenbanken. Die Zahlen zeigen deren Umfang, garantieren aber keine vollständigen Metadaten oder Skip-Intervalle für jeden Titel.

| Kennzahl | Wert |
| --- | ---: |
| Stabile Anime-Identitäten in Mapping DB | **34,851** (≈35k) |
| Externe ID-Namensräume | **55** |
| Bestätigte Cross-ID-Verbindungen | **1,225,741** |
| Normalisierte Folgen in Timestamp DB | **57,623** |
| Normalisierte Skip-Intervalle in Timestamp DB | **214,241** |

Geprüfte Snapshots vom **5. November 2026**: [Mapping DB](https://github.com/anime-db-project/anime-mapping-db/releases/tag/v2026.11.05.24) und [Timestamp DB](https://github.com/anime-db-project/anime-timestamp-db/releases/tag/v2026.11.05.8). **Rund 35.000 Titel** bedeutet 34.851 gemessene AMDB-Identitäten. Aktuelle Daten stehen in `manifest.json` der jeweiligen Releases.

Beide SQLite-Dateien lassen sich außerhalb von Telegram verwenden. Webseiten können MAL-/AniList-IDs mit Mapping DB auf AMDB-IDs abbilden und optional Timestamp DB nach Folgenintervallen abfragen. Beispiele für Python, SQLite und Exporte stehen in den Datenbank-Repositories. **Der Bot nutzt Mapping DB, bindet Timestamp DB jedoch derzeit nicht automatisch ein.**

**[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)** · **[Anime Timestamp DB](https://github.com/anime-db-project/anime-timestamp-db)**

## Funktionen

- Suche nach Titel, externer ID oder Bild mit seitenweiser Ergebnisanzeige.
- Aggregierte Bewertungen, Beschreibungen, Ausstrahlungsdaten, Besetzungen, Mitwirkende und Empfehlungen.
- Folgen, OP-/ED-Informationen und verfügbare Skip-Zeitbereiche werden bei Bedarf geladen.
- Titel werden nur über bestätigte ID-Zuordnungen zusammengeführt.
- Gespeicherte Einstellungen, Moderation, quellenspezifische Limits sowie Proxy- und User-Agent-Profile.
- Benutzeroberfläche in sieben Sprachen; Quelltexte bleiben in den verfügbaren Originalsprachen.

## Suche und Navigation

`/anime` akzeptiert Titel und explizite Anbieter-IDs. Zuerst erscheinen paginierte Treffer, anschließend die ausführliche Titelkarte. Die Suche berücksichtigt unterschiedliche Schreibweisen und Aliasse; direkte ID-Abfragen führen Datensätze jedoch niemals allein anhand des Namens zusammen.

Die Rückwärtssuche verarbeitet Telegram-Bilder oder öffentlich zugängliche Bild-URLs. Unterstützte Dienste zeigen Trefferwahrscheinlichkeit, Folge und Zeitstempel vor dem Öffnen der Karte. Gast- und API-Kontingente werden je Dienst berücksichtigt.

Die Hauptkarte zeigt normalisierte Titeldaten. Personen, Synchronsprecher, Figuren, Bilder, Bewertungsdetails, Beschreibungen, Trailer, verwandte Werke, Empfehlungen und Folgen werden bei Bedarf geladen. Staffeln, Cours und Specials erscheinen nur bei ausdrücklich vorhandener Quellstruktur.

## Datenquellen

Für Anime-Metadaten dienen MyAnimeList (Jikan ergänzend), AniList, Shikimori, Kitsu, AniDB (optionale Client-Registrierung) und AniSearch. Weitere Dienste unterstützen gezielte Zusatzfunktionen.

| Funktionen | Datenquellen |
| --- | --- |
| Suche und Metadaten | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Zusätzliche Bewertungen | [IMDb](https://www.imdb.com/) |
| Bilderkennung | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Folgen, Themes und Skip-Intervalle | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) liefert die dienstübergreifenden ID-Zuordnungen. Der SkipDB-Zeitstempelanbieter ist derzeit deaktiviert; die Quellenliste garantiert keine Abdeckung aller Titel oder Folgen.

## Fähigkeiten der Datenquellen

| Quelle | Suche | Metadaten | Mitwirkende | Figuren | Folgen | Beziehungen | Empfehlungen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch liefert mehrsprachige Ergänzungen und Synchronstimmen für bestätigte Titel, aber keine normale Titelsuche. AnimeThemes ergänzt OP/ED-Daten zu Folgen. SkipDB ist als Laufzeit-Zeitstempelquelle derzeit nicht aktiv.

## Identität und Datenzusammenführung

Keine externe Datenbank wird als allgemeine Referenz festgelegt. IDs aus MAL, AniList, Shikimori, Kitsu, AniDB und AniSearch werden erst bei bestätigter Zuordnung verbunden. Gleiche Zahlen, ähnliche Titel und Franchise-Zugehörigkeit reichen nicht aus.

Der Resolver verwendet direkte, konfliktgeprüfte Zuordnungen. Aggregierte Daten behalten ihre Herkunft, und verfügbare Ansichten erlauben Quellenauswahl. IMDb-Bewertungen benötigen eine eindeutige Beziehung zu einem Anime-ID-System; TVDB/TMDB-Brücken allein genügen nicht.

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

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

## Bereitstellung und Betrieb

Der plattformübergreifende Launcher verwaltet Umgebung, Checks, Vorder- und Hintergrundprozesse. Linux bietet zusätzlich `start.sh` mit tmux, Windows `start.ps1`/`start.cmd` und macOS `start.command`.

Docker Compose und das lokale Jikan sind optional. Die offizielle MAL-Anbindung funktioniert ohne Jikan weiter. Linux-spezifische `systemd`-Einheiten liegen unter `deploy/systemd/`.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

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

## Telegram-Befehle

`/anime` ist die zentrale Benutzerfunktion. Verwaltungsbefehle sind auf konfigurierte Telegram-IDs beschränkt. Mapping-Änderungen benötigen eine Bestätigung und werden protokolliert.

| Befehl | Zweck |
| --- | --- |
| `/start`, `/ping` | Start und Verfügbarkeit prüfen |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | Suche mit Titel, ID oder Bild |
| `/settings` | Sprache und Benutzereinstellungen |
| `/cancel` | Eingabe abbrechen |
| `/users`, `/status`, `/source_health` | Nutzerliste, System- und Quellenstatus |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | Nutzer sperren oder entsperren |
| `/mapping_overrides`, `/mapping_history [limit]` | Mapping-Überschreibungen und Historie |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | Änderungen vorbereiten, bestätigen, verwerfen |

## Konfiguration

`BOT_TOKEN` ist erforderlich. Zugangsdaten anderer Dienste sind optional: `MAL_CLIENT_ID` erweitert die MAL-Funktionen, `ANIDB_CLIENT` aktiviert AniDB. Bildsuche ist auch als Gast möglich. Proxys und User-Agents werden in `.proxies.d/` und `.user-agents.d/` konfiguriert.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Der Bot lädt geprüfte Releases von **Anime Mapping DB** und liest `mappings.db` direkt. Er baut keine Mapping-Datenbank und benötigt **Anime Timestamp DB** nicht.

## Konfigurationsreferenz

Vorlagen erzeugen `.env.d/`, ohne vorhandene Werte zu überschreiben. Nur fest definierte Dateinamen werden eingelesen. Prozessumgebungsvariablen haben Vorrang; doppelte Schlüssel in Projektdateien verhindern den Start. Geheimnisse gehören nicht ins Repository.

| Variable | Zweck |
| --- | --- |
| `BOT_TOKEN` | Erforderliches Telegram-Token |
| `MAL_CLIENT_ID` | Client-ID der offiziellen MyAnimeList API |
| `ANIDB_CLIENT` | Optionaler AniDB-HTTP-Clientname |
| `ANILIST_ACCESS_TOKEN` | Optionaler AniList-Zugriff |
| `TRACE_MOE_API_KEY` | trace.moe-Schlüssel; Gastmodus möglich |
| `WHATANIMEISTHIS_API_KEY` | What Anime Is This-Schlüssel; Gastmodus möglich |
| `ADMIN_TELEGRAM_USER_IDS` | Telegram-IDs der Administratoren |
| `TELEGRAM_BOT_API_URL` | Eigener Telegram Bot API Endpunkt |
| `MAPPINGS_DB_PATH` | Pfad der Mapping-Datenbank |
| `IMDB_RATINGS_BACKEND` | IMDb-Bewertungsmodus |
| `BAHA_ANIME_SKIP_DB_PATH` | Pfad des lokalen Baha-Index |

Für jede Datenquelle sind TOML-Proxyprofile in `.proxies.d/` möglich. HTTP, SOCKS4 und SOCKS5 werden unterstützt. Prioritäten steuern Reihenfolge und Failover; gleiche Prioritäten rotieren. Bei Ausfall aller aktiven Proxys wird nicht unbemerkt direkt verbunden.

Optionale User-Agent-Profile stehen unter `.user-agents.d/`. Änderungen an beiden Profilarten werden beim Neustart geladen. Ein eigener Telegram Bot API Server erfordert geeignete Absicherung.

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

Verfügbare Werte und Profilnamen stehen in `.env.example.d/`, `.proxies.example.d/` und `.user-agents.example.d/`.

## Lokale Daten und Wartung

Der Mapping-Updater prüft das veröffentlichte `mappings.db.zst` und seine Prüfsummen und ersetzt die lokale DB atomar, ohne auditierte Überschreibungen zu verlieren. Die Evidenzdatenbank wird für normalen Botbetrieb nicht benötigt.

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

Der lokale IMDb-Index enthält nur Bewertungen mit bestätigter Anime-Zuordnung, nicht den gesamten Dump. Baha Anime Skip wird lokal indexiert, ohne während des Botbetriebs Bahamut aufzurufen. Beide Indizes können separat gepflegt werden.

Benutzereinstellungen, bekannte Nutzer, Moderation und einzelne Quoten werden in SQLite gespeichert. Tagesprotokolle liegen unter `logs/YYYY.MM.DD/` als `bot.log`, `users.log`, `api.log` und `errors.log`; der Hintergrund-Launcher schreibt außerdem `logs/launcher.log`.

## Folgen, OP/ED und Skip-Intervalle

Episodenlisten und Zeitstempel sind unabhängige Funktionen. Die gewählte Episodenquelle legt nicht den Zeitstempeldienst fest; jeder Dienst hat eigene Kennungen und Folgenbereiche. Nicht belegbare Zuordnungen bleiben leer, statt fremde Episoden zu übernehmen.

AnimeThemes ergänzt OP-/ED-Namen, Musik, Künstler und verfügbare Videolinks. Skip-Quellen liefern Intervalle für OP, ED, Rückblick und weitere Segmente; unterschiedliche Folgenzählungen oder Schnittfassungen können abweichende Zeiten erklären. Ein Intervall aus einer Quelle ist kein allgemeiner Konsens.

## Betrieb und Fehleranalyse

Bei fehlenden Titeln zuerst Quellantwort und bestätigtes Cross-ID-Mapping prüfen. Fehlende optionale Schlüssel und einzelne API-Fehler sollen nicht die ganze Suche blockieren. `/status` zeigt Laufzeitstatistiken, `/source_health` den Zustand der Circuit Breaker.

Bei Startproblemen `doctor` und `check` aufrufen, `logs/YYYY.MM.DD/errors.log` prüfen und `BOT_TOKEN` kontrollieren. Änderungen an `.env.d/`, Proxys oder User-Agents benötigen einen Neustart. Vor dem Neuaufbau von IMDb/Baha die Mappings prüfen.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## Architektur und Ausfallsicherheit

Suche, ID-Auflösung, API-Adapter, Aggregation, Übersetzung, Speicherung und Telegram-Oberfläche sind getrennt. Timeouts, Wiederholungen, Limits und Circuit Breaker begrenzen Auswirkungen einzelner Quellausfälle.

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

## Entwicklung und Sicherheit

Beiträge sollen das konservative Identitätsmodell wahren und die Startkarte nicht unnötig mit zusätzlichen API-Aufrufen belasten. Vor PRs die Tests ausführen. Sicherheitslücken bitte nicht mit Zugangsdaten in öffentlichen Issues melden.

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md) · [Code of Conduct](../CODE_OF_CONDUCT.md)

## Dokumentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Lizenz und Quellenangaben

Der Code steht unter Apache-2.0. Für Drittanbieter-Daten gelten deren Lizenzen, Quellenpflichten und API-Bedingungen. Zugangsdaten dürfen nicht eingecheckt werden. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
