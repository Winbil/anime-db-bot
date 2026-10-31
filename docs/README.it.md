> **Progetto assistito dall'intelligenza artificiale:** questo progetto è stato sviluppato con l'aiuto dell'intelligenza artificiale.

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <strong>Italiano</strong>
</p>

# anime-db-bot

> Ricerca anime Telegram nativa dell'identità e aggregazione di metadati su MyAnimeList/Jikan, AniList, Shikimori, Kitsu, AniDB e AniSearch.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` ricerca più database di anime, risolve identità confermate tra database e crea una scheda indipendente dalla fonte senza trattare alcun database esterno come fonte canonica della verità.

Il progetto è progettato attorno a confini espliciti tra **ricerca**, **identità**, **mappature**, **fonti di metadati**, **aggregazione**, **localizzazione** e **interfaccia utente della piattaforma**. Le persone utilizzano un manifest ID/nome/ruolo leggero precaricato per i totali esatti, mentre i ritratti vengono arricchiti in batch globali delimitati; altri dati costosi come personaggi, trailer ed episodi rimangono lazy.

## Punti salienti

- **Ricerca multi-provider**: Shikimori, MyAnimeList, AniList e Kitsu vengono interrogati attraverso un flusso `/anime`.
- **Identità indipendente dall'origine** — `AnimeIdentity` memorizza gli ID esterni del peer; non esiste un ID del database primario globale.
- **Mappatura incrociata conservativa**: la mappatura runtime è solo diretta e riconosce i conflitti, con provenienza e sostituzioni controllate manualmente.
- **Schede di metadati aggregati**: i valori provenienti da fonti di metadati di successo vengono normalizzati e uniti mentre viene preservata la provenienza specifica della fonte.
- **Manifest + arricchimento lazy**: ID, nomi e ruoli dello staff/seiyuu vengono precaricati come un elenco esatto e leggero; i ritratti vengono arricchiti in lotti globali (50 per impostazione predefinita), mentre personaggi, screenshot, popolarità dettagliata, descrizioni/sfondi, trailer ed episodi rimangono lazy.
- **Livello di resilienza condiviso**: errori di origine digitati, nuovi tentativi, interruttori automatici, ripristino semiaperto, limiti di velocità e ciclo di vita HTTP condiviso.
- **Impostazioni persistenti con ambito piattaforma**: le impostazioni internazionali dell'utente, gli utenti conosciuti e lo stato di moderazione sono archiviati in SQLite.
- **Sette lingue dell'interfaccia utente**: l'inglese è la lingua predefinita/di riserva; Russo, giapponese, tedesco, spagnolo, francese e italiano sono completamente selezionabili in `/settings`.
- **Dati di uscita e proiezioni**: vengono aggregati classificazione per età, stato di messa in onda, episodi trasmessi/totali e data del prossimo episodio fornita dalle fonti; gli anime TV in corso con totale noto ricevono stime settimanali chiaramente indicate per tutti gli episodi rimanenti.
- **Controlli orientati alla produzione** — Python 3.11–3.14 CI, Ruff, controlli del formattatore, ambito mypy, gate di copertura e ShellCheck.

## Capacità di origine

| Fonte | Cerca | Metadati | Persone | Personaggi | Trailer | Episodi | Schermate | Popolarità | Descrizione |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu è una fonte pubblica JSON:API nativa dell'identità. Le richieste GET pubbliche di sola lettura non richiedono OAuth credenziali; gli ID confermati Kitsu partecipano già a `mappings.db` e Kitsu possono anche restituire mappature MAL/AniList/AniDB dirette con risultati di ricerca e metadati. Kitsu attualmente fornisce ricerca, metadati, popolarità, descrizioni, episodi e un trailer di YouTube quando disponibile. Le persone/personaggi non vengono pubblicizzati intenzionalmente perché tali relazioni sono spesso scarse.

AniDB è opzionale ed è abilitato solo quando è configurato `ANIDB_CLIENT`. Jikan **non** è un database di identità separato: è un backend MAL locale utilizzato per i dati che non sono disponibili tramite il MAL ufficiale API. I suoi concessori di licenza della carta principale e le statistiche sulla popolarità lazy utilizzano endpoint locali separati, quindi lo scraping della distribuzione del punteggio non è nel percorso iniziale della carta. AniSearch è un'origine del database API nativa dell'identità risolta attraverso i bordi di mappatura confermati `anisearch`. Il suo pubblico API non espone la normale ricerca della query del titolo, quindi non si unisce al percorso di ricerca veloce `/anime <title>`. Poiché AniSearch inserisce ID e `/full` nello stesso rigido gruppo di limitazione, l'origine esegue un recupero `/full` memorizzato nella cache per titolo e mantiene i campi pesanti fuori dall'aggregazione iniziale; persone, personaggi ed episodi riutilizzano successivamente lo stesso carico utile senza un'altra attesa della rete. Le localizzazioni in inglese, giapponese, tedesco, spagnolo, francese e italiano AniSearch vengono utilizzate per titoli/sinonimi localizzati, sinossi, titoli di episodi, licenziatari regionali e crediti vocali. Le richieste pubbliche senza token vengono calcolate in base all'intervallo documentato di famiglia di ID di 10 secondi (5 secondi con un token valido) e il testo sinossi di origine AniSearch mantiene il collegamento di attribuzione diretto AniSearch richiesto. Il supporto SkipDB rimane nel codebase come fornitore dormiente supportato da IMDb, ma non è intenzionalmente registrato nel runtime perché l'attuale copertura dei segmenti saltati dell'anime è troppo piccola per giustificarne l'esposizione nell'interfaccia utente. Il suo parser/impostazioni/test vengono conservati in modo che possano essere riattivati ​​in seguito se la copertura migliora. SkipDB i dati vengono serviti sotto ODbL 1.0 + reciprocità.

## Come funziona

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

### Regole di identità

`AnimeIdentity` non ha un ID primario. Non si presuppone mai che un ID numerico di un database identifichi lo stesso titolo in un altro database semplicemente perché il numero corrisponde.

L'unione tra sorgenti segue regole prudenti:

1. gli ID esterni condivisi espliciti sono una forte prova di identità;
2. ID in conflitto dello stesso fornitore impediscono una fusione;
3. la ricerca testuale può utilizzare un fallback romaji normalizzato esatto vincolato solo quando non esiste alcun conflitto con lo stesso fornitore;
4. la ricerca diretta dell'ID **non** utilizza l'unione del solo titolo;
5. le mappature di runtime sono solo dirette e non attraversano ricorsivamente catene arbitrarie di stile TVDB/TMDB.

L'identità completamente arricchita rimane disponibile internamente per il routing e le funzionalità lazy. Il blocco ID visibile della carta mostra solo gli ID appartenenti alle origini dei metadati che hanno effettivamente contribuito a quella carta.

## Ricerca

L'unico comando di ricerca rivolto all'utente è `/anime`.

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
/anime kitsu:<id>
```

`/anime <title>` interroga tutti i provider di ricerca registrati in parallelo e raccoglie un set di risultati con ambito query limitato prima dell'impaginazione Telegram. La pertinenza considera titoli, alias, varianti native/romaji, corrispondenze token/prefisso, traslitterazione e un fallback conservativo di somiglianza.

I limiti rigidi di pagine/articoli proteggono le quote upstream. Quando il bot non è in grado di dimostrare che il conteggio raccolto è definitivo, l'interfaccia utente segnala un conteggio incompleto invece di presentarlo come esatto.

L'esecuzione di `/anime` senza argomenti apre un selettore di sorgente interattivo. L'input in sospeso ha come ambito la coppia utente/chat, scade automaticamente e può essere annullato con `/cancel`.

`/anime` supporta anche la ricerca inversa delle immagini. Allega un'immagine al comando o passa un URL di immagine pubblica e il bot offrirà solo backend di ricerca di immagini la cui quota è attualmente disponibile: trace.moe, What Anime Is This o entrambi. I risultati vengono risolti tramite AniList ID confermati e mostrati come la normale anteprima del candidato impaginato; la scheda completa dei metadati viene aperta solo dopo che l'utente ha scelto **Dettagli**. Le prove corrispondenti (fornitore, somiglianza, episodio, timestamp) vengono conservate nell'anteprima. L'azione **Non è il titolo che ti serve?** consente il tentativo o l'annullamento di un'altra fonte senza bypassare le quote del provider. Le immagini raster caricate vengono normalizzate in JPEG prima della ricerca in uscita.

Le credenziali per la ricerca di immagini sono facoltative. trace.moe funziona in modo anonimo quando `TRACE_MOE_API_KEY` è vuoto e legge la quota corrente reale da `/me`; le chiavi configurate vengono inviate come `x-trace-key`, quindi le quote partner/donatori vengono scoperte anziché codificate. What Anime Is This viene eseguito come ospite quando `WHATANIMEISTHIS_API_KEY` è vuoto e utilizza `Authorization: Bearer ...` quando è presente una chiave. Poiché il suo pubblico API non espone lo stato del credito con API tasti, il bot mantiene un contatore giornaliero locale persistente e conservativo: le impostazioni predefinite sono 5 ricerche degli ospiti e 10 ricerche con API chiavi, ed entrambi i massimali sono configurabili per account con diverse politiche di credito. Impostare `WHATANIMEISTHIS_API_DAILY_LIMIT=0` per disabilitare il limite locale dei tasti API e fare affidamento sugli errori di credito/quota del servizio. Una risposta di quota lato server contrassegna immediatamente il backend non disponibile per il periodo di quota locale corrente.

## Sezioni lazy della scheda

La scheda principale rimane incentrata sui metadati. Le seguenti sezioni vengono caricate solo quando richiesto:

- personale e creatori;
- doppiatori, inclusi crediti doppiati con tag linguistici AniSearch;
- personaggi e ritratti;
- screenshot;
- distribuzioni dettagliate di popolarità/classifica;
- descrizioni e testo di sfondo della fonte;
- trailer/promo;
- episodi.

I crediti vocali giapponesi rimangono la base di riferimento nella lingua originale senza tag. AniSearch crediti doppiati vengono conservati con i suffissi di ruolo espliciti `[EN]`, `[DE]`, `[ES]`, `[FR]` o `[IT]` in modo che non vengano mai mascherati da crediti giapponesi originali. Il personale di localizzazione/ADR è escluso dall'elenco del personale di produzione primaria.

## Requisiti e supporto della piattaforma

Il runtime Python è progettato per **Linux, macOS e nativo Windows** con Python **3.11, 3.12, 3.13 o 3.14**. GitHub Actions esegue la suite di unità completa su tutte e tre le famiglie di sistemi operativi per ogni versione Python supportata.

- **Linux** — piattaforma di produzione primaria; il launcher multipiattaforma funziona sulle distribuzioni tradizionali purché sia ​​disponibile una build CPython supportata. Il `start.sh` in bundle rimane un assistente di produzione `tmux` orientato a Linux.
- **macOS** — supportato tramite il launcher Python; `start.command` viene fornito come involucro conveniente. `systemd` le unità di manutenzione non si applicano su macOS.
- **Windows (nativo)** — supportato tramite il launcher Python, `start.ps1` o `start.cmd`; WSL non è richiesto.
- **Docker + Docker Compose** — opzionale su ogni piattaforma e utilizzato solo per il supplemento locale Jikan. Il bot funziona ancora senza Docker; il MAL ufficiale rimane disponibile mentre le funzionalità supplementari solo per Jikan sono disabilitate.
- **systemd**: integrazione opzionale di distribuzione/manutenzione solo per Linux in `deploy/systemd/`.

Esegui `python scripts/project.py doctor` (o lo stesso comando con il tuo interprete Python attivo) per verificare la compatibilità di runtime/dipendenza di base di una macchina.

## Avvio rapido

Clonare prima il repository:

```text
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Il launcher canonico è `scripts/project.py`. Crea `.venv`, installa dipendenze bloccate, crea directory di configurazione mancanti dagli esempi impegnati senza sovrascrivere i valori esistenti e comprende il layout nativo dell'ambiente virtuale su Unix e Windows.

Linux / macOS:

```bash
python3 scripts/project.py setup
# Edit .env.d/telegram.env and add at least BOT_TOKEN.
python3 scripts/project.py check
python3 scripts/project.py run       # foreground
python3 scripts/project.py start     # background + PID file
```

Windows PowerShell/Prompt dei comandi:

```powershell
py -3 scripts\project.py setup
# Edit .env.d\telegram.env and add at least BOT_TOKEN.
py -3 scripts\project.py check
py -3 scripts\project.py run
.\start.ps1                         # background
```

`start.cmd` è disponibile per il prompt dei comandi e macOS può utilizzare `./start.command`. I processi in background avviati dal launcher multipiattaforma vengono gestiti con:

```text
python scripts/project.py status
python scripts/project.py stop
python scripts/project.py restart
```

Linux le distribuzioni di produzione possono continuare a utilizzare `./start.sh`; preserva il flusso di lavoro `tmux` distaccato esistente. I log di runtime rimangono sotto `logs/YYYY.MM.DD/`, mentre il generico launcher in background scrive anche il suo stdout/stderr ereditato su `logs/launcher.log`.

I registri di runtime sono suddivisi per responsabilità in `logs/YYYY.MM.DD/`: `bot.log` contiene eventi applicazione/runtime, `users.log` contiene Telegram traccia delle azioni dell'utente, `api.log` contiene eventi di origine/API/riprova/integrità in uscita e `errors.log` duplica tutti i `ERROR+` record per una diagnostica rapida. La directory cambia automaticamente dopo la mezzanotte locale senza riavviare il bot.

## Configurazione

Tutta l'analisi dell'ambiente di runtime è centralizzata in `core/settings.py`. Le nuove distribuzioni copiano da `.env.example.d/` a `.env.d/`. Vengono caricati solo i file fissi `telegram.env`, `sources.env`, `timestamps.env`, `rate-limits.env`, `mappings.env`, `storage.env`, `logging.env` e `runtime.env`; i file vaganti come `backup.env` vengono ignorati. Le chiavi duplicate nei file di configurazione del progetto non riescono all'avvio, mentre le variabili dell'ambiente del processo reale hanno la massima priorità. Un `.env` monolitico rimane supportato solo come percorso di migrazione.

### Impostazioni essenziali

| Variabile | Obbligatorio | Scopo |
| --- | :---: | --- |
| `BOT_TOKEN` | Sì | Telegram token bot di BotFather. |
| `MAL_CLIENT_ID` | Consigliato | Abilita la ricerca MyAnimeList e i metadati ufficiali. |
| `ANIDB_CLIENT` | No | Abilita AniDB HTTP API metadati/persone/episodi. |
| `ANIDB_CLIENT_VERSION` | No | Versione client registrata AniDB HTTP API; il valore predefinito è `1`. |
| `ANILIST_ACCESS_TOKEN` | No | Token AniList facoltativo quando si desidera l'accesso autenticato. |
| `KITSU_API_URL` | No | Kitsu pubblico JSON:API URL di base; il valore predefinito è `https://kitsu.io/api/edge`. |
| `TRACE_MOE_API_KEY` | No | Tasto opzionale trace.moe API (`x-trace-key`); la modalità gratuita funziona senza di essa e la quota viene letta da `/me`. |
| `WHATANIMEISTHIS_API_KEY` | No | Chiave opzionale What Anime Is This API inviata come `Authorization: Bearer ...`; la modalità ospite gratuita funziona senza di essa. |
| `IMAGE_SEARCH_DB_PATH` | No | SQLite percorso per la contabilità conservativa delle quote di ricerca di immagini persistenti. |
| `ADMIN_TELEGRAM_USER_IDS` | No | ID utente amministratore separati da virgola/spazio/punto e virgola. |
| `TELEGRAM_BOT_API_URL` | No | Endpoint Telegram Bot API personalizzato/auto-ospitato. |
| `TELEGRAM_BOT_API_LOCAL_FILE_ROOT` | No | Directory host mappata su `/var/lib/telegram-bot-api` quando i percorsi dei file locali del Bot API si trovano all'interno di un contenitore. |
| `USER_SETTINGS_DB_PATH` | No | SQLite percorso per le impostazioni per utente e il registro degli utenti conosciuti. |
| `BANS_DB_PATH` | No | SQLite percorso per divieti di moderazione. |
| `MAPPINGS_DB_PATH` | No | Database di mappatura cross-ID runtime. |

Non impegnare `.env`, `.env.d/`, `.proxies.d/`, token bot, token di accesso, password, credenziali proxy o credenziali private API.

### Pool di proxy per origine

Il routing proxy in uscita opzionale è configurato separatamente in `.proxies.d/`, un file TOML fisso per origine runtime più `telegram.toml` per il bot stesso. Inizia da `.proxies.example.d/`. Gli schemi proxy supportati sono `http`, `socks4` e `socks5`.

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

I profili sono indipendenti: `mal.toml` influisce solo su MAL, `anilist.toml` solo AniList e così via. I valori più alti `priority` vengono provati prima dei valori più bassi indipendentemente dall'ordine TOML. Le iscrizioni con la stessa priorità vengono selezionate nel girone all'italiana; i livelli con priorità inferiore vengono utilizzati solo come failover dopo il guasto del livello superiore. Gli URL proxy duplicati sono consentiti quando hanno nomi di voci distinti, quindi la ripetizione di un endpoint può dargli intenzionalmente un peso di rotazione maggiore. `enabled = false` può disabilitare l'intero profilo o una singola voce. Se almeno una voce proxy è attiva per un profilo, quel profilo **non** torna silenziosamente alla connessione diretta quando tutti i proxy falliscono; l'accesso diretto viene utilizzato solo quando il profilo non ha proxy attivi. La configurazione del proxy viene caricata all'avvio del processo, quindi le modifiche diventano effettive dopo il riavvio del bot. Quando `telegram.toml` ha proxy attivi, questo bot ignora intenzionalmente qualsiasi endpoint `telegram-bot-api` locale/condiviso configurato e comunica con il `api.telegram.org` ufficiale attraverso il proprio pool di proxy; ciò mantiene l'ambito proxy su questo bot invece di modificare altri bot che condividono il server locale. Anche `jikan.toml` è speciale: l'hop Python al servizio loopback Jikan rimane diretto, mentre il proxy selezionato viene inoltrato al servizio Jikan locale e applicato al suo scrape in uscita MyAnimeList.

I profili di runtime fissi sono: `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `bahamut`, `baha_anime_skip`, `skipdb`, `trace_moe` e `whatanimeisthis`. I file TOML sporadici vengono ignorati. I file proxy possono contenere credenziali e sono gitignorati; `start.sh` mantiene `.proxies.d` in modalità `700` e i file di profilo conosciuti in modalità `600`.

### Profili utente-agente per origine

L'agente utente facoltativo esegue l'override sotto `.user-agents.d/` con gli stessi nomi di profilo fissi del routing proxy. Se un profilo non ha una voce personalizzata attiva, le richieste utilizzano lo User-Agent del progetto integrato (`anime-db-bot/<version> (...)`). Il valore più alto `priority` vince; le voci legate alla priorità attiva più alta ruotano tra le richieste. Gli User-Agent con priorità più bassa rimangono in standby finché le voci con priorità più alta non vengono disabilitate.

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

Il limite di rete sovrascrive le intestazioni `User-Agent` locali del provider, quindi il valore del profilo selezionato è autorevole. Per `jikan`, l'agente utente selezionato viene inoltrato tramite il servizio di loopback e applicato alla sua richiesta in uscita MyAnimeList. Per `telegram`, uno User-Agent personalizzato attivo commuta questo bot da un endpoint condiviso/locale `telegram-bot-api` all'ufficiale `api.telegram.org`, assicurando che l'intestazione configurata raggiunga la richiesta esterna Telegram. `.user-agents.d` viene gitignorato e caricato all'avvio del processo.

### AniDB

L'integrazione utilizza AniDB HTTP API. Richiede un HTTP API **nome e versione del client** registrato, non una password dell'account AniDB.

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

AniDB Le risposte XML vengono memorizzate nella cache sul disco e le richieste di rete vengono serializzate con un intervallo minimo di richiesta aggiuntivo per rispettare le aspettative API del servizio.

### MAL / Jikan

MAL è l'origine dell'identità. Jikan è un backend supplementare locale e non introduce mai una chiave di identità `jikan`.

Il servizio in bundle è disponibile sotto:

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Un'interruzione Jikan non rende la ricerca/metadati MAL ufficiali non disponibili.

## Comandi

### Comandi dell'utente

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

### Comandi di amministrazione

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

Le mutazioni di mappatura sono intenzionalmente in due fasi. `/mapping_set` e `/mapping_delete` creano una mutazione in sospeso di breve durata; il database cambia solo dopo `/mapping_confirm <token>`. La cronologia di controllo registra l'amministratore Telegram responsabile della modifica.

## Localizzazione

Il modello di dominio è indipendente dalle impostazioni locali. Gli adattatori di origine normalizzano i valori upstream di stato/tipo/stagione/genere/ruolo in chiavi canoniche e la traduzione avviene solo al momento del rendering.

Impostazioni locali dell'interfaccia utente supportate:

- `en` — Inglese (**predefinito e fallback**);
- `ru` — Русский;
- `ja` — 日本語;
- `de` — Tedesco;
- `es` — spagnolo;
- `fr` — Francese;
- `it` — Italiano.

Gli utenti esistenti mantengono le impostazioni internazionali salvate esplicitamente. Nuovi utenti, impostazioni mancanti, valori locali non validi e chiavi di traduzione mancanti ricadono nell'inglese.

Il testo sorgente in formato libero, come le descrizioni degli anime, non è tradotto automaticamente. Vedi [`localization/README.md`](../localization/README.md) per l'architettura di localizzazione e le regole di manutenzione.

## Persistenza

Il runtime mantiene separati i diversi tipi di stato:

- impostazioni utente e utenti conosciuti - SQLite, ambito da `(platform, user_id)`;
- divieti: archivio persistente separato SQLite;
- `mappings.db`: database del risolutore cross-ID supportato da disco;
- AniDB XML: cache del disco;
- Telegram Sessioni di callback di ricerca/scheda: stato TTL/LRU in memoria limitato.

Le impostazioni utente legacy create prima dell'ambito della piattaforma vengono trasferite come record Telegram senza modificare le impostazioni locali salvate.

## Resilienza e limitazione della velocità

In uscita HTTP utilizza istanze condivise `httpx.AsyncClient` di proprietà di `AppContext`. Gli errori all'origine vengono normalizzati in errori tipizzati e passati attraverso un livello comune di tentativi/interruttore.

Il registro sanitario di origine supporta:

- gestione dei guasti transitori e non transitori;
- tentativi limitati con backoff;
- soglie degli interruttori automatici;
- tempi di recupero;
- esattamente una sonda di recupero semiaperta.

I limiti personali Telegram sono limitati a `(platform, user_id)`. Gli amministratori possono bypassare il limitatore personale, ma **mai** bypassare i limiti di sicurezza del provider upstream.

## Architettura

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

`services/runtime/app_context.py` è la radice della composizione dell'applicazione. Le dipendenze del runtime di produzione dovrebbero essere possedute lì anziché create come singleton del servizio in fase di importazione.

Maggiori dettagli: [`docs/app-context.md`](app-context.md).

## Mappature ID incrociati

Il programma di aggiornamento della mappatura trasmette diversi set di dati esterni in SQLite, registra provenienza/prove/conflitti, convalida il database ricostruito e lo scambia atomicamente nella sua posizione. Il grafico completo non viene caricato nella RAM.

Le sostituzioni direzionali manuali supportano `accept` e `reject`, trasportano metadati di autore/motivo/marca temporale e preservano la cronologia di sola aggiunta tra le ricostruzioni.

I comandi di manutenzione sono disponibili tramite il launcher multipiattaforma:

```text
python scripts/project.py mappings --status
python scripts/project.py mappings --override-list
python scripts/project.py mappings --override-history
```

Il wrapper Unix `./scripts/update-mappings.sh` rimane disponibile per le distribuzioni esistenti.

## Sviluppo

Utilizza lo stesso launcher su ogni sistema operativo supportato:

```text
python scripts/project.py setup --dev
python scripts/project.py check
python scripts/project.py doctor
```

Su Windows, `py -3 scripts\project.py ...` può essere utilizzato al posto di `python`. I file Unix `./scripts/setup.sh` e `./scripts/check.sh` sono comodi wrapper attorno alla stessa implementazione. I comandi diretti dell'ambiente virtuale rimangono disponibili a `.venv/bin/python` su Unix e `.venv\Scripts\python.exe` su Windows.

GitHub Le azioni richiedono che l'intera suite di unità venga trasmessa a **Ubuntu, macOS e Windows** per Python 3.11, 3.12, 3.13 e 3.14. Ogni lavoro della matrice esegue anche il medico di avvio multipiattaforma. Il lavoro di qualità Linux esegue inoltre Ruff controlli di correttezza, controlli di formattazione per la base tipizzata, mypy per la base tipizzata, test completi con un gate di copertura di almeno il 70% e ShellCheck per i wrapper di shell Unix.

## Collaboratori

- [OpenAI Codex](https://github.com/apps/openai-codex) — app GitHub ufficiale di Codex; sviluppo e implementazione del progetto assistiti dall’IA.

## Contribuire

I contributi sono benvenuti. Leggi [CONTRIBUTING.md](../CONTRIBUTING.md) prima di aprire una richiesta pull e segui il [Codice di condotta](../CODE_OF_CONDUCT.md) del progetto. Le segnalazioni di bug e le richieste di funzionalità devono utilizzare i moduli per i problemi del repository.

## Sicurezza

- Mantieni `.env` e le credenziali fuori dal controllo della versione.
- I log utilizzano file `bot/users/api/errors` giornalieri, redazione segreta per impostazione predefinita, ID di correlazione per aggiornamento, timestamp del fuso orario locale di runtime e rotazione limitata per file. `LOG_REDACT_SECRETS=0` disabilita deliberatamente tutto il mascheramento per la diagnostica locale e può scrivere le credenziali parola per parola; mantenerlo abilitato sui registri condivisi/pubblici.
- Le azioni riservate all'amministratore devono rimanere dietro il livello di controllo dell'accesso.
- Non esporre pubblicamente un Telegram Bot API self-hosted, futuri endpoint di parametri o futuri API esterni pubblicamente senza controlli espliciti di autenticazione/rete.
- Le sostituzioni della mappatura vengono controllate perché un bordo di identità errato può influire su più funzionalità.

Per la segnalazione delle vulnerabilità e i canali di sicurezza supportati, vedere [SECURITY.md](../SECURITY.md). Non pubblicare credenziali, token o dettagli di distribuzione privata in un problema pubblico.

## Stato del progetto

Il progetto è in fase di sviluppo attivo. Vengono implementati il ​​flusso di ricerca/carta principale Telegram, il modello di identità, il database di mappatura, l'aggregazione multi-sorgente, la localizzazione, le capacità lazy, la persistenza, la resilienza e la base CI. Sono previsti lavori aggiuntivi di rilevamento/ricerca, integrazioni di account utente, notifiche, monitoraggio/metriche Prometheus, supporto esterno API/Mini App e altre fonti.

## Licenza

Concesso in licenza con [Licenza Apache 2.0](../LICENSE). Puoi utilizzare, modificare e distribuire il progetto secondo i suoi termini; conservare gli avvisi richiesti e contrassegnare le modifiche significative come richiesto dalla licenza.

## Fonti dei dati e riconoscimenti

`anime-db-bot` si integra o si basa su dati provenienti da progetti e servizi, tra cui:

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Kitsu](https://kitsu.app/) - sola lettura pubblica JSON:API; no OAuth richiesto per le normali richieste GET
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) - Metadati del database API; si applicano i requisiti di attribuzione e collegamento alla sinossi
- [SkipDB](https://skipdb.tv/) - dati salta segmento in ODbL 1.0 + reciprocità

I dati di mappatura Cross-ID vengono assemblati da più set di dati della comunità. Ciascun servizio e set di dati upstream rimane soggetto ai propri termini, limiti di tariffa e requisiti di attribuzione.

Kitsu richieste GET pubbliche di sola lettura vengono utilizzate senza OAuth credenziali. Il runtime applica i propri limiti di richiesta conservativi perché non si presuppone alcun contratto con limite di velocità lato server stabile.

AniSearch Database API le richieste di metadati di sola lettura non richiedono OAuth. `ANISEARCH_APP_ID` e `ANISEARCH_APP_SECRET` sono credenziali dell'applicazione facoltative OAuth riservate per future funzionalità AniSearch autorizzate dall'utente; non vengono mai inviati con richieste di database di sola lettura.
