> **Progetto sviluppato con l'aiuto dell'IA.**

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <strong>Italiano</strong>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

Bot Telegram per cercare anime in database indipendenti e riunire schede, episodi, personaggi, staff e opere correlate in un'unica interfaccia.

## L'ecosistema in numeri

Il bot appartiene a una famiglia di database anime utilizzabili indipendentemente. Le cifre mostrano la dimensione dei progetti, non garantiscono dati completi o timestamp per ogni titolo.

| Indicatore | Valore |
| --- | ---: |
| Identità anime stabili in Mapping DB | **34,851** (≈35k) |
| Namespace di ID esterni | **55** |
| Collegamenti ID accettati | **1,225,741** |
| Episodi normalizzati in Timestamp DB | **57,623** |
| Intervalli normalizzati in Timestamp DB | **214,241** |

Snapshot verificati del **5 novembre 2026**: [Mapping DB](https://github.com/anime-db-project/anime-mapping-db/releases/tag/v2026.11.05.24) e [Timestamp DB](https://github.com/anime-db-project/anime-timestamp-db/releases/tag/v2026.11.05.8). **Circa 35.000 titoli** corrisponde a 34.851 identità AMDB misurate. Per i valori recenti leggere i `manifest.json` delle release.

I database SQLite sono utilizzabili anche fuori da Telegram. Un sito può convertire ID MAL/AniList tramite Mapping DB e poi consultare facoltativamente i segmenti di Timestamp DB. I repository contengono esempi Python, SQL e di esportazione. **Il bot utilizza Mapping DB, ma non integra automaticamente Timestamp DB.**

**[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)** · **[Anime Timestamp DB](https://github.com/anime-db-project/anime-timestamp-db)**

## Funzionalità

- Ricerca per titolo, ID esterno o immagine con risultati paginati.
- Valutazioni, trame, trasmissione, cast, staff, relazioni e consigli aggregati.
- Episodi, informazioni OP/ED e intervalli saltabili disponibili, caricati su richiesta.
- Associazione prudente dei titoli solo tramite ID verificati.
- Preferenze persistenti, moderazione, limiti per fonte, profili proxy e User-Agent.
- Interfaccia in sette lingue; i testi delle fonti restano nelle lingue disponibili.

## Ricerca e navigazione

`/anime` accetta un titolo o un ID esplicito di un provider. I risultati sono paginati prima di aprire la scheda. La ricerca considera alias e grafie diverse, ma la ricerca diretta per ID non unisce mai titoli soltanto per somiglianza del nome.

La ricerca inversa accetta immagini Telegram o URL pubblici. I provider disponibili presentano somiglianza, episodio e istante prima di aprire la scheda. Le quote ospite e API sono gestite separatamente per fonte.

La scheda principale contiene dati normalizzati. Staff, doppiatori, personaggi, immagini, statistiche, descrizioni, trailer, opere correlate, consigli ed episodi vengono caricati a richiesta. Stagioni e speciali sono raggruppati solo se la fonte ne fornisce la struttura.

## Fonti dei dati

I metadati provengono da MyAnimeList (con Jikan come integrazione), AniList, Shikimori, Kitsu, AniDB (registrazione client facoltativa) e AniSearch. Altri servizi forniscono funzioni specifiche.

| Funzionalità | Fonti dei dati |
| --- | --- |
| Ricerca e metadati | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Valutazioni aggiuntive | [IMDb](https://www.imdb.com/) |
| Ricerca tramite immagine | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Episodi, sigle e intervalli | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) fornisce le corrispondenze fra ID di servizi diversi. Il provider di intervalli SkipDB è attualmente disattivato; l'elenco delle fonti non garantisce dati per tutti i titoli o episodi.

## Funzionalità delle fonti

| Fonte | Ricerca | Metadati | Staff | Personaggi | Episodi | Relazioni | Consigli |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch arricchisce i titoli verificati con testi localizzati e doppiatori, ma non è un motore di ricerca per titolo. AnimeThemes aggiunge dati OP/ED agli episodi. SkipDB non è attivo nel runtime.

## Identità e aggregazione

Nessun catalogo esterno è assunto come autorità universale. Gli ID di MAL, AniList, Shikimori, Kitsu, AniDB e AniSearch sono collegati solo con evidenza verificata. Numeri uguali, titoli simili o la stessa serie non bastano.

Il resolver usa soltanto collegamenti diretti e controlla i conflitti. L'aggregazione conserva l'origine di ogni dato e, ove disponibili, viste delle singole fonti. Le valutazioni IMDb richiedono una corrispondenza univoca con un ID anime; il solo passaggio TVDB/TMDB non è sufficiente.

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

## Avvio rapido

Richiede Python 3.11–3.14 su Linux, macOS o Windows. Clona il repository e utilizza il launcher multipiattaforma:

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# Inserisci BOT_TOKEN in .env.d/telegram.env
python3 scripts/project.py check
python3 scripts/project.py run
```

Su Windows usa `py -3 scripts\project.py` al posto di `python3 scripts/project.py`. Per l'esecuzione in background usa `python3 scripts/project.py start` (disponibili anche `status`, `restart`, `stop`); su Linux è disponibile `./start.sh`.

## Distribuzione e gestione

Il launcher multipiattaforma gestisce ambiente virtuale, controlli e processi. Linux include `start.sh` con tmux, Windows `start.ps1`/`start.cmd`, macOS `start.command`.

Docker Compose e Jikan locale sono opzionali. La fonte MAL ufficiale resta operativa senza Jikan. Le unità `systemd` in `deploy/systemd/` sono destinate a Linux.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

## Utilizzo

`/anime` permette di selezionare una fonte o cercare per titolo. Un'immagine allegata a `/anime` o un URL pubblico avvia la ricerca inversa se disponibile. `/settings` modifica le preferenze; `/cancel` annulla l'input.

```text
/anime Frieren
/anime mal:5114
/anime anilist:<id>
/anime shikimori:<id>
/settings
/ping
/cancel
```

## Comandi Telegram

`/anime` è la funzione principale. I comandi amministrativi richiedono ID Telegram autorizzati; le modifiche ai mapping prevedono conferma e storico di audit.

| Comando | Scopo |
| --- | --- |
| `/start`, `/ping` | Avvio e verifica |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | Ricerca per titolo, ID o immagine |
| `/settings` | Lingua e preferenze |
| `/cancel` | Annullare inserimento in attesa |
| `/users`, `/status`, `/source_health` | Utenti, stato bot e delle fonti |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | Bloccare o sbloccare utenti |
| `/mapping_overrides`, `/mapping_history [limit]` | Esaminare eccezioni e storico |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | Preparare, confermare o annullare modifiche |

## Configurazione

`BOT_TOKEN` è obbligatorio. Le altre credenziali sono facoltative: `MAL_CLIENT_ID` estende MyAnimeList, `ANIDB_CLIENT` abilita AniDB. La ricerca per immagini è possibile anche come ospite. Proxy e User-Agent si configurano in `.proxies.d/` e `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Il bot scarica e verifica le release di **Anime Mapping DB**, utilizzando direttamente `mappings.db`. Non genera i mapping e non richiede **Anime Timestamp DB**.

## Riferimento configurazione

I modelli vengono copiati in `.env.d/` senza sovrascrivere la configurazione esistente. Si leggono solo file con nomi previsti. Le variabili dell'ambiente di processo hanno precedenza; chiavi duplicate nei file causano errore. Non conservare segreti in Git.

| Variabile | Scopo |
| --- | --- |
| `BOT_TOKEN` | Token Telegram obbligatorio |
| `MAL_CLIENT_ID` | Client ID di MyAnimeList ufficiale |
| `ANIDB_CLIENT` | Client HTTP AniDB facoltativo |
| `ANILIST_ACCESS_TOKEN` | Accesso AniList autenticato facoltativo |
| `TRACE_MOE_API_KEY` | Chiave trace.moe, modalità ospite |
| `WHATANIMEISTHIS_API_KEY` | Chiave What Anime Is This, modalità ospite |
| `ADMIN_TELEGRAM_USER_IDS` | ID Telegram autorizzati come amministratori |
| `TELEGRAM_BOT_API_URL` | Endpoint Telegram Bot API personalizzato |
| `MAPPINGS_DB_PATH` | Percorso del DB di mapping |
| `IMDB_RATINGS_BACKEND` | Modalità per i voti IMDb |
| `BAHA_ANIME_SKIP_DB_PATH` | Percorso dell'indice Baha |

Ogni fonte può avere un profilo TOML in `.proxies.d/` con HTTP, SOCKS4 e SOCKS5. Priorità, rotazione a parità di livello e failover definiscono l'uso. Se tutti i proxy attivi falliscono non avviene un passaggio silenzioso alla rete diretta.

I profili User-Agent si configurano in `.user-agents.d/`. Le modifiche diventano attive dopo il riavvio. Un server Telegram Bot API privato è facoltativo e va protetto.

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

Variabili e nomi dei profili disponibili sono nei modelli `.env.example.d/`, `.proxies.example.d/` e `.user-agents.example.d/`.

## Dati locali e manutenzione

L'aggiornamento controlla `mappings.db.zst` e i checksum, sostituisce atomicamente il database e conserva le eccezioni amministrative registrate. Il bot non necessita del database delle evidenze.

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

L'indice IMDb locale conserva solo i voti associati a ID anime verificati, non l'intero dump. Baha Anime Skip usa un indice locale senza chiamare Bahamut a runtime. Entrambi possono essere aggiornati separatamente.

Preferenze, utenti noti, moderazione e alcune quote vengono archiviate in SQLite. I log giornalieri sono in `logs/YYYY.MM.DD/` con `bot.log`, `users.log`, `api.log`, `errors.log`; il launcher scrive anche `logs/launcher.log`.

## Episodi, OP/ED e intervalli

Elenco episodi e intervalli sono funzionalità indipendenti. La fonte scelta per gli episodi non impone quale provider fornisce i timestamp: ciascuno usa identificatori e numerazioni propri. Se un legame non è verificato, è preferibile nessun dato a un episodio sbagliato.

AnimeThemes completa gli episodi con sigle OP/ED, canzoni, artisti e collegamenti video. I provider dei timestamp possono offrire intervalli per opening, ending, riepiloghi e altri segmenti; montaggi e numerazioni differenti possono cambiare i tempi. Un intervallo non implica un consenso.

## Gestione e diagnosi

Quando un titolo non viene trovato controllare la fonte e i mapping verificati. Un API irraggiungibile o una credenziale facoltativa assente non deve bloccare tutta la ricerca. `/status` mostra le statistiche, `/source_health` lo stato dei circuit breaker.

Se il processo non parte eseguire `doctor` e `check`, leggere `logs/YYYY.MM.DD/errors.log` e verificare `BOT_TOKEN`. Modifiche a `.env.d/`, proxy e User-Agent richiedono riavvio. Prima di ricreare IMDb/Baha verificare lo stato dei mapping.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## Architettura e affidabilità

Ricerca, identità, client delle fonti, aggregazione, localizzazione, persistenza e interfaccia Telegram sono separati. Timeout, tentativi, limiti e circuit breaker isolano gli errori dei singoli provider.

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

## Sviluppo e sicurezza

I contributi devono preservare i controlli di identità ed evitare chiamate superflue nella scheda iniziale. Eseguire i test prima delle PR. Segnalare i problemi di sicurezza senza esporre credenziali in issue pubbliche.

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md) · [Code of Conduct](../CODE_OF_CONDUCT.md)

## Documentazione

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Licenza e attribuzioni

Codice sotto Apache-2.0. Servizi e dati di terzi mantengono le proprie licenze, gli obblighi di attribuzione e i termini delle API. Non inserire credenziali nei commit. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
