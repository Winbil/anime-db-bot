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

## Funzionalità

- Ricerca per titolo, ID esterno o immagine con risultati paginati.
- Valutazioni, trame, trasmissione, cast, staff, relazioni e consigli aggregati.
- Episodi, informazioni OP/ED e intervalli saltabili disponibili, caricati su richiesta.
- Associazione prudente dei titoli solo tramite ID verificati.
- Preferenze persistenti, moderazione, limiti per fonte, profili proxy e User-Agent.
- Interfaccia in sette lingue; i testi delle fonti restano nelle lingue disponibili.

## Fonti dei dati

I metadati provengono da MyAnimeList (con Jikan come integrazione), AniList, Shikimori, Kitsu, AniDB (registrazione client facoltativa) e AniSearch. Altri servizi forniscono funzioni specifiche.

| Funzionalità | Fonti dei dati |
| --- | --- |
| Ricerca e metadati | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Valutazioni aggiuntive | [IMDb](https://www.imdb.com/) |
| Ricerca tramite immagine | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Episodi, sigle e intervalli | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) fornisce le corrispondenze fra ID di servizi diversi. Il provider di intervalli SkipDB è attualmente disattivato; l'elenco delle fonti non garantisce dati per tutti i titoli o episodi.

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

## Configurazione

`BOT_TOKEN` è obbligatorio. Le altre credenziali sono facoltative: `MAL_CLIENT_ID` estende MyAnimeList, `ANIDB_CLIENT` abilita AniDB. La ricerca per immagini è possibile anche come ospite. Proxy e User-Agent si configurano in `.proxies.d/` e `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Il bot scarica e verifica le release di **Anime Mapping DB**, utilizzando direttamente `mappings.db`. Non genera i mapping e non richiede **Anime Timestamp DB**.

## Documentazione

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Licenza e attribuzioni

Codice sotto Apache-2.0. Servizi e dati di terzi mantengono le proprie licenze, gli obblighi di attribuzione e i termini delle API. Non inserire credenziali nei commit. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
