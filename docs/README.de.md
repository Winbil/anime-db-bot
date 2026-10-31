> **KI-unterstütztes Projekt:** Dieses Projekt wurde mit Hilfe von KI entwickelt.

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <strong>Deutsch</strong> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

> Identitätsnative Telegram Anime-Suche und Metadatenaggregation über MyAnimeList/Jikan, AniList, Shikimori, Kitsu, AniDB und AniSearch.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` durchsucht mehrere Anime-Datenbanken, löst bestätigte datenbankübergreifende Identitäten auf und erstellt eine quellenunabhängige Karte, ohne eine externe Datenbank als kanonische Quelle der Wahrheit zu behandeln.

Das Projekt ist um explizite Grenzen zwischen **Suche**, **Identität**, **Zuordnungen**, **Metadatenquellen**, **Aggregation**, **Lokalisierung** und **Plattform-Benutzeroberfläche** herum konzipiert. Für genaue Gesamtzahlen verwenden Menschen ein vorab abgerufenes, vereinfachtes ID-/Namen-/Rollenmanifest, während Porträts in begrenzten globalen Stapeln angereichert werden. Andere teure Daten wie Charaktere, Trailer und Episoden bleiben unberücksichtigt.

## Höhepunkte

- **Multi-Provider-Suche** – Shikimori, MyAnimeList, AniList und Kitsu werden über einen `/anime`-Flow abgefragt.
- **Quellenunabhängige Identität** – `AnimeIdentity` speichert externe Peer-IDs; Es gibt keine globale primäre Datenbank-ID.
- **Konservative Cross-ID-Zuordnung** – Die Laufzeitzuordnung ist nur direkt und konfliktbewusst, mit Herkunft und manuell geprüften Überschreibungen.
- **Aggregierte Metadatenkarten** – Werte aus erfolgreichen Metadatenquellen werden normalisiert und zusammengeführt, während die quellenspezifische Herkunft erhalten bleibt.
- **Manifest + Lazy Enrichment** – Personal-/Seiyuu-IDs, Namen und Rollen werden als leichtgewichtiger, exakter Dienstplan vorab abgerufen; Porträts werden in globalen Stapeln (standardmäßig 50) angereichert, während Charaktere, Screenshots, detaillierte Beliebtheit, Beschreibungen/Hintergründe, Trailer und Episoden lazy bleiben.
- **Gemeinsame Resilienzschicht** – typisierte Quellfehler, Wiederholungsversuche, Leistungsschalter, halboffene Wiederherstellung, Ratenbegrenzungen und gemeinsamer HTTP-Lebenszyklus.
- **Persistente plattformbezogene Einstellungen** – Benutzergebietsschema, bekannte Benutzer und Moderationsstatus werden in SQLite gespeichert.
- **Sieben UI-Sprachen** – Englisch ist das Standard-/Fallback-Gebietsschema; Russisch, Japanisch, Deutsch, Spanisch, Französisch und Italienisch sind in `/settings` vollständig wählbar.
- **Veröffentlichungsdaten und Prognosen** – Altersfreigabe, Ausstrahlungsstatus, ausgestrahlte/Gesamtfolgen und von Quellen gelieferte Termine der nächsten Folge werden aggregiert; laufende TV-Anime mit bekannter Gesamtzahl erhalten klar gekennzeichnete wöchentliche Schätzungen für alle verbleibenden Folgen.
- **Produktionsorientierte Prüfungen** – Python 3.11–3.14 CI, Ruff, Formatiererprüfungen, Mypy-Bereich, Coverage Gate und ShellCheck.

## Quellfähigkeiten

| Quelle | Suche | Metadaten | Menschen | Charaktere | Trailer | Episoden | Screenshots | Popularität | Beschreibung |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu ist eine identitätsnative öffentliche JSON:API-Quelle. Öffentliche schreibgeschützte GET-Anfragen erfordern keine OAuth Anmeldeinformationen; Bestätigte Kitsu-IDs nehmen bereits an `mappings.db` teil, und Kitsu kann auch direkte MAL/AniList/AniDB-Zuordnungen mit Suchergebnissen und Metadaten zurückgeben. Kitsu steuert derzeit Suche, Metadaten, Beliebtheit, Beschreibungen, Episoden und einen YouTube-Trailer bei, sofern verfügbar. Personen/Charaktere werden bewusst nicht beworben, da diese Beziehungen oft spärlich sind.

AniDB ist optional und wird nur aktiviert, wenn `ANIDB_CLIENT` konfiguriert ist. Jikan ist **keine** separate Identitätsdatenbank: Es handelt sich um ein lokales MAL-Backend, das für Daten verwendet wird, die nicht über die offizielle MAL API verfügbar sind. Die Hauptkartenlizenzgeber und Lazy Popularity-Statistiken verwenden separate lokale Endpunkte, sodass das Scraping der Punkteverteilung nicht auf dem anfänglichen Kartenpfad erfolgt. AniSearch ist eine identitätsnative Datenbankquelle API, die durch bestätigte `anisearch`-Zuordnungskanten aufgelöst wird. Sein öffentliches API stellt keine normale Titelabfragesuche zur Verfügung, sodass es nicht in den schnellen `/anime <title>`-Suchpfad aufgenommen wird. Da AniSearch ID und `/full` in dieselbe strenge Drosselungsgruppe einfügt, führt die Quelle einen zwischengespeicherten `/full`-Abruf pro Titel durch und hält schwere Felder von der anfänglichen Aggregation fern; Personen, Charaktere und Episoden verwenden später dieselbe Nutzlast wieder, ohne dass eine weitere Netzwerkwartezeit erforderlich ist. Lokalisierungen in Englisch, Japanisch, Deutsch, Spanisch, Französisch und Italienisch AniSearch werden für lokalisierte Titel/Synonyme, Synopsen, Episodentitel, regionale Lizenzgeber und Sprachnachweise verwendet. Öffentliche No-Token-Anfragen werden auf das dokumentierte 10-Sekunden-ID-Familienintervall (5 Sekunden mit einem gültigen Token) beschränkt, und der aus AniSearch stammende Zusammenfassungstext behält den erforderlichen direkten AniSearch-Zuordnungslink bei. Die SkipDB-Unterstützung verbleibt in der Codebasis als ruhender, von IMDb unterstützter Anbieter, wird jedoch absichtlich nicht in der Laufzeit registriert, da die aktuelle Anime-Skip-Segment-Abdeckung zu gering ist, um eine Offenlegung in der Benutzeroberfläche zu rechtfertigen. Der Parser/die Einstellungen/Tests bleiben erhalten, sodass er später wieder aktiviert werden kann, wenn sich die Abdeckung verbessert. SkipDB-Daten werden unter ODbL 1,0 + Reziprozität bereitgestellt.

## Wie es funktioniert

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

### Identitätsregeln

`AnimeIdentity` hat keine primäre ID. Es wird niemals davon ausgegangen, dass eine numerische ID aus einer Datenbank denselben Titel in einer anderen Datenbank identifiziert, nur weil die Nummer übereinstimmt.

Die quellenübergreifende Zusammenführung folgt konservativen Regeln:

1. explizit geteilte externe IDs sind ein starker Identitätsbeweis;
2. widersprüchliche IDs desselben Anbieters verhindern eine Zusammenführung;
3. Die Textsuche kann nur dann einen eingeschränkten, exakt normalisierten Romaji-Fallback verwenden, wenn kein Konflikt mit demselben Anbieter besteht.
4. Bei der Direkt-ID-Suche wird **nicht** nur die Titelzusammenführung verwendet;
5. Laufzeitzuordnungen sind nur direkt und durchlaufen keine rekursiven beliebigen Ketten im TVDB/TMDB-Stil.

Die vollständige erweiterte Identität bleibt intern für Routing- und Lazy-Funktionen verfügbar. Der sichtbare ID-Block der Karte zeigt nur IDs an, die zu Metadatenquellen gehören, die tatsächlich zu dieser Karte beigetragen haben.

## Suchen

Der einzige benutzerorientierte Suchbefehl ist `/anime`.

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
/anime kitsu:<id>
```

`/anime <title>` fragt alle registrierten Suchanbieter parallel ab und sammelt vor der Telegram Paginierung eine begrenzte, abfragebezogene Ergebnismenge. Die Relevanz berücksichtigt Titel, Aliase, native/romaji-Varianten, Token-/Präfix-Übereinstimmungen, Transliteration und einen konservativen Ähnlichkeits-Fallback.

Feste Seiten-/Elementobergrenzen schützen Upstream-Kontingente. Wenn der Bot nicht nachweisen kann, dass die erfasste Zählung endgültig ist, meldet die Benutzeroberfläche eine unvollständige Zählung, anstatt sie als genau darzustellen.

Wenn Sie `/anime` ohne Argumente ausführen, wird eine interaktive Quellenauswahl geöffnet. Ausstehende Eingaben sind auf das Benutzer/Chat-Paar beschränkt, laufen automatisch ab und können mit `/cancel` abgebrochen werden.

`/anime` unterstützt auch die umgekehrte Bildsuche. Hängen Sie ein Bild an den Befehl an oder übergeben Sie eine öffentliche Bild-URL und der Bot bietet nur Bildsuch-Backends an, deren Kontingent derzeit verfügbar ist: trace.moe, What Anime Is This oder beides. Die Ergebnisse werden durch bestätigte AniList IDs aufgelöst und als normale paginierte Kandidatenvorschau angezeigt; Die vollständige Metadatenkarte wird erst geöffnet, nachdem der Benutzer **Details** ausgewählt hat. Übereinstimmende Beweise (Anbieter, Ähnlichkeit, Episode, Zeitstempel) werden in der Vorschau gespeichert. Die Aktion **Nicht der Titel, den Sie benötigen?** ermöglicht einen weiteren Quellversuch oder einen Abbruch, ohne die Anbieterkontingente zu umgehen. Hochgeladene Rasterbilder werden vor der ausgehenden Suche auf JPEG normalisiert.

Anmeldeinformationen für die Bildsuche sind optional. trace.moe läuft anonym, wenn `TRACE_MOE_API_KEY` leer ist und liest das tatsächliche aktuelle Kontingent von `/me`; Konfigurierte Schlüssel werden als `x-trace-key` gesendet, sodass Partner-/Spenderquoten ermittelt und nicht fest codiert werden. What Anime Is This läuft als Gast, wenn `WHATANIMEISTHIS_API_KEY` leer ist und verwendet `Authorization: Bearer ...`, wenn ein Schlüssel vorhanden ist. Da sein öffentlicher API den API-Schlüssel-Kreditstatus nicht offenlegt, unterhält der Bot einen konservativen, dauerhaften lokalen Tageszähler: Die Standardwerte sind 5 Gastsuchen und 10 API-Schlüsselsuchen, und beide Obergrenzen sind für Konten mit unterschiedlichen Kreditrichtlinien konfigurierbar. Legen Sie `WHATANIMEISTHIS_API_DAILY_LIMIT=0` fest, um die lokale API-Schlüsselobergrenze zu deaktivieren und sich auf die eigenen Kredit-/Kontingentfehler des Dienstes zu verlassen. Eine serverseitige Kontingentantwort markiert sofort, dass dieses Backend für den aktuellen lokalen Kontingentzeitraum nicht verfügbar ist.

## Faule Kartenabschnitte

Auf der Hauptkarte stehen die Metadaten an erster Stelle. Die folgenden Abschnitte werden nur auf Anfrage geladen:

- Mitarbeiter und Schöpfer;
- Synchronsprecher, einschließlich sprachgekennzeichneter AniSearch Synchronsprecher;
- Charaktere und Porträts;
- Screenshots;
- detaillierte Beliebtheits-/Rankingverteilungen;
- Beschreibungen und Quellhintergrundtext;
- Trailer/Promos;
- Episoden.

Die japanischen Sprachnachweise bleiben die unbeschriftete Basisversion der Originalsprache. AniSearch-Dub-Credits werden mit expliziten `[EN]`-, `[DE]`-, `[ES]`-, `[FR]`- oder `[IT]`-Rollensuffixen beibehalten, sodass sie nie als originale japanische Credits getarnt werden. Lokalisierungs-/ADR-Personal ist von der Liste der primären Produktionsmitarbeiter ausgeschlossen.

## Anforderungen und Plattformunterstützung

Die Python-Laufzeit ist für **Linux, macOS und native Windows** mit Python **3.11, 3.12, 3.13 oder 3.14** konzipiert. GitHub Actions führt die vollständige Einheitensuite auf allen drei Betriebssystemfamilien für jede unterstützte Python Version aus.

- **Linux** – primäre Produktionsplattform; Der plattformübergreifende Launcher funktioniert auf Mainstream-Distributionen, solange ein unterstützter CPython-Build verfügbar ist. Der gebündelte `start.sh` bleibt ein Linux-orientierter `tmux`-Produktionshelfer.
- **macOS** – unterstützt durch den Python Launcher; `start.command` wird als praktischer Wrapper bereitgestellt. `systemd` Wartungseinheiten gelten nicht für macOS.
- **Windows (nativ)** – unterstützt durch den Python Launcher, `start.ps1` oder `start.cmd`; WSL ist nicht erforderlich.
- **Docker + Docker Compose** – optional auf jeder Plattform und nur für die lokale Jikan-Ergänzung verwendet. Der Bot funktioniert immer noch ohne Docker; Das offizielle MAL bleibt verfügbar, während nur Jikan-Zusatzfunktionen deaktiviert sind.
- **systemd** – optionale Linux-nur Bereitstellungs-/Wartungsintegration unter `deploy/systemd/`.

Führen Sie `python scripts/project.py doctor` (oder denselben Befehl mit Ihrem aktiven Python-Interpreter) aus, um die grundlegende Laufzeit-/Abhängigkeitskompatibilität einer Maschine zu überprüfen.

## Schnellstart

Klonen Sie zuerst das Repository:

```text
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Der kanonische Launcher ist `scripts/project.py`. Es erstellt `.venv`, installiert gesperrte Abhängigkeiten, erstellt fehlende Konfigurationsverzeichnisse aus den festgeschriebenen Beispielen, ohne vorhandene Werte zu überschreiben, und versteht das native Layout der virtuellen Umgebung unter Unix und Windows.

Linux / macOS:

```bash
python3 scripts/project.py setup
# Edit .env.d/telegram.env and add at least BOT_TOKEN.
python3 scripts/project.py check
python3 scripts/project.py run       # foreground
python3 scripts/project.py start     # background + PID file
```

Windows PowerShell / Eingabeaufforderung:

```powershell
py -3 scripts\project.py setup
# Edit .env.d\telegram.env and add at least BOT_TOKEN.
py -3 scripts\project.py check
py -3 scripts\project.py run
.\start.ps1                         # background
```

`start.cmd` ist für die Eingabeaufforderung verfügbar und macOS kann `./start.command` verwenden. Vom plattformübergreifenden Launcher gestartete Hintergrundprozesse werden verwaltet mit:

```text
python scripts/project.py status
python scripts/project.py stop
python scripts/project.py restart
```

Linux Produktionsbereitstellungen verwenden möglicherweise weiterhin `./start.sh`; Es behält den vorhandenen getrennten `tmux`-Workflow bei. Laufzeitprotokolle bleiben unter `logs/YYYY.MM.DD/`, während der generische Hintergrund-Launcher auch sein geerbtes stdout/stderr in `logs/launcher.log` schreibt.

Laufzeitprotokolle werden nach Zuständigkeit unter `logs/YYYY.MM.DD/` aufgeteilt: `bot.log` enthält Anwendungs-/Laufzeitereignisse, `users.log` enthält Telegram Benutzeraktionsverfolgung, `api.log` enthält ausgehende Quell-/API/Wiederholungs-/Gesundheitsereignisse und `errors.log` dupliziert alle `ERROR+`-Datensätze für eine schnelle Diagnose. Das Verzeichnis wechselt automatisch nach lokaler Mitternacht, ohne den Bot neu zu starten.

## Konfiguration

Die gesamte Analyse der Laufzeitumgebung ist in `core/settings.py` zentralisiert. Neue Bereitstellungen kopieren `.env.example.d/` nach `.env.d/`. Es werden nur die festen Dateien `telegram.env`, `sources.env`, `timestamps.env`, `rate-limits.env`, `mappings.env`, `storage.env`, `logging.env` und `runtime.env` geladen; Streudateien wie `backup.env` werden ignoriert. Doppelte Schlüssel in Projektkonfigurationsdateien schlagen beim Start fehl, während echte Prozessumgebungsvariablen die höchste Priorität haben. Ein monolithisches `.env` wird weiterhin nur als Migrationspfad unterstützt.

### Wesentliche Einstellungen

| Variable | Erforderlich | Zweck |
| --- | :---: | --- |
| `BOT_TOKEN` | Ja | Telegram Bot-Token von BotFather. |
| `MAL_CLIENT_ID` | Empfohlen | Ermöglicht offizielle MyAnimeList Suche und Metadaten. |
| `ANIDB_CLIENT` | Nein | Aktiviert AniDB HTTP API Metadaten/Personen/Episoden. |
| `ANIDB_CLIENT_VERSION` | Nein | Registrierte AniDB HTTP API Client-Version; Der Standardwert ist `1`. |
| `ANILIST_ACCESS_TOKEN` | Nein | Optionales AniList-Token, wenn authentifizierter Zugriff gewünscht ist. |
| `KITSU_API_URL` | Nein | Kitsu öffentliche JSON:API Basis-URL; Der Standardwert ist `https://kitsu.io/api/edge`. |
| `TRACE_MOE_API_KEY` | Nein | Optionale Taste trace.moe API (`x-trace-key`); Der freie Modus funktioniert auch ohne und das Kontingent wird ab `/me` gelesen. |
| `WHATANIMEISTHIS_API_KEY` | Nein | Optionaler What Anime Is This API Schlüssel gesendet als `Authorization: Bearer ...`; Der kostenlose Gastmodus funktioniert auch ohne. |
| `IMAGE_SEARCH_DB_PATH` | Nein | SQLite Pfad für die konservative Quotenabrechnung für die dauerhafte Bildsuche. |
| `ADMIN_TELEGRAM_USER_IDS` | Nein | Durch Komma/Leerzeichen/Semikolon getrennte Telegram Admin-Benutzer-IDs. |
| `TELEGRAM_BOT_API_URL` | Nein | Benutzerdefinierter/selbstgehosteter Telegram Bot API Endpunkt. |
| `TELEGRAM_BOT_API_LOCAL_FILE_ROOT` | Nein | Das Hostverzeichnis ist `/var/lib/telegram-bot-api` zugeordnet, wenn sich die Dateipfade des lokalen Bot API in einem Container befinden. |
| `USER_SETTINGS_DB_PATH` | Nein | SQLite Pfad für benutzerspezifische Einstellungen und Registrierung bekannter Benutzer. |
| `BANS_DB_PATH` | Nein | SQLite Pfad für Moderationsverbote. |
| `MAPPINGS_DB_PATH` | Nein | Laufzeit-Cross-ID-Mapping-Datenbank. |
| `BAHA_ANIME_SKIP_DB_PATH` | Nein | Lokaler SQLite-Index für Baha-Anime-Skip-Zeitmarken; zur Laufzeit erfolgen dafür keine Bahamut/Baha-Netzwerkanfragen. |

Übertragen Sie keine `.env`, `.env.d/`, `.proxies.d/`, Bot-Tokens, Zugriffstoken, Passwörter, Proxy-Anmeldeinformationen oder privaten API-Anmeldeinformationen.

### Lokaler Baha-Anime-Skip-Index

Baha Anime Skip wird aus einem lokalen SQLite-Snapshot gelesen, nicht über HTTP zur Laufzeit. Nach dem Erstellen von `mappings.db` kann der Index explizit gebaut oder aktualisiert werden:

```bash
python scripts/project.py baha-index
```

Der Builder lädt den archivierten Datensatz einmal, verwendet bestätigte `bahamut`-IDs aus `mappings.db`, ordnet Episoden ihren `videoSn`-Werten zu und schreibt atomar `data/baha_anime_skip.sqlite3`. Der Bot liest danach nur diese SQLite-Datei; ohne bestätigtes Mapping oder Indexeintrag gibt die Quelle leer zurück, ohne Netzwerk-Fallback.

### Proxy-Pools pro Quelle

Das optionale Outbound-Proxy-Routing wird separat unter `.proxies.d/` konfiguriert, eine feste TOML-Datei pro Laufzeitquelle plus `telegram.toml` für den Bot selbst. Beginnen Sie mit `.proxies.example.d/`. Unterstützte Proxy-Schemata sind `http`, `socks4` und `socks5`.

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

Profile sind unabhängig: `mal.toml` betrifft nur MAL, `anilist.toml` nur AniList und so weiter. Höhere `priority`-Werte werden unabhängig von der TOML-Reihenfolge vor niedrigeren Werten ausprobiert. Einträge mit gleicher Priorität werden im Round-Robin-Verfahren ausgewählt; Ebenen mit niedrigerer Priorität werden nur als Failover verwendet, nachdem die höhere Ebene ausgefallen ist. Doppelte Proxy-URLs sind zulässig, wenn sie unterschiedliche Eintragsnamen haben, sodass die Wiederholung eines Endpunkts ihm absichtlich mehr Rotationsgewicht verleihen kann. `enabled = false` kann entweder das gesamte Profil oder einen einzelnen Eintrag deaktivieren. Wenn mindestens ein Proxy-Eintrag für ein Profil aktiv ist, greift dieses Profil **nicht** stillschweigend auf die direkte Verbindung zurück, wenn alle Proxys ausfallen; Der direkte Zugriff wird nur verwendet, wenn das Profil keine aktiven Proxys hat. Die Proxy-Konfiguration wird beim Prozessstart geladen, sodass Änderungen nach einem Bot-Neustart wirksam werden. Wenn `telegram.toml` aktive Proxys hat, umgeht dieser Bot absichtlich jeden konfigurierten lokalen/gemeinsamen `telegram-bot-api`-Endpunkt und kommuniziert mit dem offiziellen `api.telegram.org` über seinen eigenen Proxy-Pool; Dadurch bleibt der Proxy auf diesen Bot beschränkt, anstatt andere Bots zu ändern, die den lokalen Server gemeinsam nutzen. `jikan.toml` ist auch etwas Besonderes: Der Python-Hop zum Loopback-Dienst Jikan bleibt direkt, während der ausgewählte Proxy an den lokalen Jikan-Dienst weitergeleitet und auf dessen ausgehenden MyAnimeList-Scrape angewendet wird.

Feste Laufzeitprofile sind: `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `skipdb`, `trace_moe` und `whatanimeisthis`. Verirrte TOML-Dateien werden ignoriert. Proxydateien können Anmeldeinformationen enthalten und werden ignoriert. `start.sh` behält `.proxies.d` im Modus `700` und bekannte Profildateien im Modus `600`.

### Benutzer-Agent-Profile pro Quelle

Optionale User-Agent-Überschreibungen live unter `.user-agents.d/` mit denselben festen Profilnamen wie Proxy-Routing. Wenn ein Profil keinen aktiven benutzerdefinierten Eintrag hat, verwenden Anfragen den integrierten Projekt-User-Agent (`anime-db-bot/<version> (...)`). Höhere `priority`-Gewinne; Einträge mit der höchsten aktiven Priorität wechseln zwischen den Anforderungen. Benutzeragenten mit niedrigerer Priorität bleiben im Standby-Modus, bis Einträge mit höherer Priorität deaktiviert werden.

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

Die Netzwerkgrenze überschreibt die anbieterlokalen `User-Agent`-Header, sodass der ausgewählte Profilwert maßgeblich ist. Für `jikan` wird der ausgewählte User-Agent über den Loopback-Dienst weitergeleitet und auf seine ausgehende MyAnimeList-Anfrage angewendet. Für `telegram` schaltet ein aktiver benutzerdefinierter Benutzeragent diesen Bot von einem gemeinsam genutzten/lokalen `telegram-bot-api`-Endpunkt zum offiziellen `api.telegram.org` um und stellt so sicher, dass der konfigurierte Header die externe Telegram-Anfrage erreicht. `.user-agents.d` wird beim Prozessstart ignoriert und geladen.

### AniDB

Die Integration verwendet AniDB HTTP API. Es erfordert einen registrierten HTTP API **Clientnamen und eine Version**, kein AniDB Kontopasswort.

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

AniDB XML-Antworten werden auf der Festplatte zwischengespeichert und Netzwerkanforderungen werden mit einem zusätzlichen Mindestanforderungsintervall serialisiert, um die API Erwartungen des Dienstes zu erfüllen.

### MAL / Jikan

MAL ist die Identitätsquelle. Jikan ist ein lokales ergänzendes Backend und führt niemals einen `jikan` Identitätsschlüssel ein.

Der gebündelte Dienst läuft unter:

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Ein Jikan-Ausfall führt nicht dazu, dass die offizielle MAL-Suche/Metadaten nicht mehr verfügbar ist.

## Befehle

### Benutzerbefehle

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

### Admin-Befehle

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

Kartierungsmutationen erfolgen absichtlich zweistufig. `/mapping_set` und `/mapping_delete` erzeugen eine kurzlebige ausstehende Mutation; die Datenbank ändert sich erst nach `/mapping_confirm <token>`. Der Prüfverlauf zeichnet den Telegram Administrator auf, der für die Änderung verantwortlich ist.

## Lokalisierung

Das Domänenmodell ist gebietsschemaneutral. Quelladapter normalisieren Upstream-Status-/Typ-/Saison-/Genre-/Rollenwerte in kanonische Schlüssel, und die Übersetzung erfolgt nur zum Zeitpunkt des Renderns.

Unterstützte UI-Gebietsschemata:

- `en` – Englisch (**Standard und Fallback**);
- `ru` — Russisch;
- `ja` — 日本語;
- `de` — Deutsch;
- `es` – Spanisch;
- `fr` – Französisch;
- `it` – Italienisch.

Bestehende Benutzer behalten ihr explizit gespeichertes Gebietsschema. Neue Benutzer, fehlende Einstellungen, ungültige Gebietsschemawerte und fehlende Übersetzungsschlüssel greifen auf Englisch zurück.

Freiform-Quelltexte wie Anime-Beschreibungen werden nicht maschinell übersetzt. Siehe [`localization/README.md`](../localization/README.md) für Lokalisierungsarchitektur und Wartungsregeln.

## Beharrlichkeit

Die Laufzeit trennt verschiedene Arten von Zuständen:

- Benutzereinstellungen und bekannte Benutzer – SQLite, begrenzt durch `(platform, user_id)`;
- Verbote – separater persistenter SQLite-Speicher;
- `mappings.db` – festplattengestützte Cross-ID-Resolver-Datenbank;
- AniDB XML – Festplatten-Cache;
- Telegram Such-/Kartenrückrufsitzungen – begrenzter TTL/LRU-Status im Arbeitsspeicher.

Ältere Benutzereinstellungen, die vor der Festlegung des Plattformbereichs erstellt wurden, werden als Telegram-Datensätze migriert, ohne dass ihr gespeichertes Gebietsschema geändert wird.

## Belastbarkeit und Ratenbegrenzung

Ausgehend HTTP verwendet gemeinsam genutzte `httpx.AsyncClient` Instanzen im Besitz von `AppContext`. Quellausfälle werden in typisierte Fehler normalisiert und durch eine gemeinsame Wiederholungs-/Leistungsschalterschicht geleitet.

Das Quellgesundheitsregister unterstützt:

- Umgang mit vorübergehenden und nicht vorübergehenden Fehlern;
- begrenzte Wiederholungsversuche mit Backoff;
- Schwellenwerte für Leistungsschalter;
- Abklingzeiten;
- genau eine halboffene Wiederherstellungssonde.

Persönliche Telegram-Limits gelten pro `(platform, user_id)`. Administratoren können die persönliche Beschränkung umgehen, aber **niemals** die Sicherheitsgrenzen der Upstream-Anbieter umgehen.

## Architektur

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

`services/runtime/app_context.py` ist das Stammverzeichnis der Anwendungszusammensetzung. Abhängigkeiten zur Produktionslaufzeit sollten sich dort befinden und nicht als Service-Singletons zur Importzeit erstellt werden.

Weitere Einzelheiten: [`docs/app-context.md`](app-context.md).

## Cross-ID-Zuordnungen

Der Mapping-Updater streamt mehrere externe Datensätze in SQLite, zeichnet Herkunft/Beweise/Konflikte auf, validiert die neu erstellte Datenbank und tauscht sie atomar aus. Der vollständige Graph wird nicht in den RAM geladen.

Manuelle Richtungsüberschreibungen unterstützen `accept` und `reject`, übertragen Autor/Ursache/Zeitstempel-Metadaten und bewahren den Nur-Anhänge-Verlauf über Neuerstellungen hinweg.

Wartungsbefehle sind über den plattformübergreifenden Launcher verfügbar:

```text
python scripts/project.py mappings --status
python scripts/project.py mappings --override-list
python scripts/project.py mappings --override-history
```

Der Unix `./scripts/update-mappings.sh`-Wrapper bleibt für bestehende Bereitstellungen verfügbar.

## Entwicklung

Verwenden Sie auf jedem unterstützten Betriebssystem denselben Launcher:

```text
python scripts/project.py setup --dev
python scripts/project.py check
python scripts/project.py doctor
```

Bei Windows kann `py -3 scripts\project.py ...` anstelle von `python` verwendet werden. Die Unix-Dateien `./scripts/setup.sh` und `./scripts/check.sh` sind praktische Wrapper für dieselbe Implementierung. Direkte Befehle für die virtuelle Umgebung sind weiterhin unter `.venv/bin/python` unter Unix und `.venv\Scripts\python.exe` unter Windows verfügbar.

Für GitHub Aktionen ist die vollständige Einheitensuite erforderlich, um **Ubuntu, macOS und Windows** für Python 3.11, 3.12, 3.13 und 3.14 weiterzugeben. Jeder Matrixjob führt auch den plattformübergreifenden Launcher Doctor aus. Der Linux-Qualitätsjob führt zusätzlich Ruff-Korrektheitsprüfungen, Formatterprüfungen für die typisierte Grundlage, Mypy für die typisierte Grundlage, vollständige Tests mit einem Coverage Gate von mindestens 70 % und ShellCheck für Unix-Shell-Wrapper durch.

## Mitwirkende

- [OpenAI Codex](https://github.com/apps/openai-codex) — offizielle GitHub-App von Codex; KI-gestützte Entwicklung und Implementierung des Projekts.

## Mitwirken

Beiträge sind willkommen. Lesen Sie [CONTRIBUTING.md](../CONTRIBUTING.md), bevor Sie eine Pull-Anfrage öffnen, und befolgen Sie den Projekt-[Verhaltenskodex](../CODE_OF_CONDUCT.md). Für Fehlerberichte und Funktionsanfragen sollten die Repository-Problemformulare verwendet werden.

## Sicherheit

- Halten Sie `.env` und Anmeldeinformationen außerhalb der Versionskontrolle.
- Protokolle verwenden tägliche `bot/users/api/errors`-Dateien, standardmäßig geheime Schwärzung, Korrelations-IDs pro Update, laufzeitlokale Zeitzonen-Zeitstempel und eine begrenzte Rotation pro Datei. `LOG_REDACT_SECRETS=0` deaktiviert absichtlich jegliche Maskierung für die lokale Diagnose und schreibt Anmeldeinformationen möglicherweise wörtlich; Lassen Sie es in freigegebenen/öffentlichen Protokollen aktiviert.
- Nur-Administrator-Aktionen müssen hinter der Zugriffskontrollebene bleiben.
- Stellen Sie einen selbstgehosteten Telegram Bot API, einen zukünftigen Metrikendpunkt oder einen zukünftigen externen API nicht öffentlich ohne explizite Authentifizierung/Netzwerkkontrollen zur Verfügung.
- Zuordnungsüberschreibungen werden überwacht, da ein falscher Identitätsrand mehrere Funktionen beeinträchtigen kann.

Informationen zu Schwachstellenberichten und unterstützten Sicherheitskanälen finden Sie unter [SECURITY.md](../SECURITY.md). Veröffentlichen Sie keine Anmeldeinformationen, Token oder privaten Bereitstellungsdetails in einer öffentlichen Ausgabe.

## Projektstatus

Das Projekt befindet sich in aktiver Entwicklung. Der Kern Telegram Such-/Kartenfluss, Identitätsmodell, Zuordnungsdatenbank, Multi-Source-Aggregation, Lokalisierung, Lazy-Funktionen, Persistenz, Belastbarkeit und CI-Grundlage sind implementiert. Weitere Erkennungs-/Suchfilter, Benutzerkontointegrationen, Benachrichtigungen, Überwachung/Prometheus-Metriken, externe API/Mini-App-Unterstützung und weitere Quellen sind geplant.

## Lizenz

Lizenziert unter der [Apache-Lizenz 2.0](../LICENSE). Sie dürfen das Projekt gemäß seinen Bedingungen nutzen, ändern und verbreiten; Bewahren Sie die erforderlichen Hinweise auf und kennzeichnen Sie wesentliche Änderungen als in der Lizenz erforderlich.

## Datenquellen und Danksagungen

`anime-db-bot` lässt sich in Daten aus Projekten und Diensten integrieren oder baut darauf auf, einschließlich:

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Kitsu](https://kitsu.app/) – öffentlich schreibgeschützt JSON:API; kein OAuth für normale GET-Anfragen erforderlich
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) – Datenbank API Metadaten; Es gelten die Anforderungen hinsichtlich Namensnennung und Synopsis-Link
- [SkipDB](https://skipdb.tv/) – Daten zum Überspringen von Segmenten unter ODbL 1,0 + Reziprozität

Cross-ID-Mapping-Daten werden aus mehreren Community-Datensätzen zusammengestellt. Jeder Upstream-Dienst und Datensatz unterliegt weiterhin seinen eigenen Bedingungen, Ratenbeschränkungen und Zuordnungsanforderungen.

Kitsu öffentliche schreibgeschützte GET-Anfragen werden ohne OAuth Anmeldeinformationen verwendet. Die Laufzeit wendet ihre eigenen konservativen Anforderungslimits an, da kein stabiler serverseitiger Ratenlimitvertrag angenommen wird.

AniSearch Datenbank API Nur-Lese-Metadatenanfragen erfordern kein OAuth. `ANISEARCH_APP_ID` und `ANISEARCH_APP_SECRET` sind optional OAuth Anwendungsanmeldeinformationen, die für zukünftige vom Benutzer autorisierte AniSearch Funktionen reserviert sind; Sie werden niemals mit schreibgeschützten Datenbankanforderungen gesendet.
