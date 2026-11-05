> **Projet développé avec l'aide de l'IA.**

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <strong>Français</strong> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

Bot Telegram permettant de rechercher des anime dans des bases indépendantes et de regrouper fiches, épisodes, personnages, équipe de production et œuvres associées.

## Fonctionnalités

- Recherche par titre, identifiant externe ou image avec pagination.
- Notes, synopsis, diffusion, distribution, équipe, relations et recommandations regroupés.
- Épisodes, informations OP/ED et plages à ignorer disponibles, chargés à la demande.
- Fusion prudente des titres uniquement lorsque les identifiants sont confirmés.
- Préférences persistantes, modération, limites par source, profils proxy et User-Agent.
- Interface en sept langues, sans modifier les textes originaux des sources.

## Sources de données

Les métadonnées proviennent de MyAnimeList (Jikan en complément), AniList, Shikimori, Kitsu, AniDB (enregistrement client facultatif) et AniSearch. D'autres services sont utilisés pour des fonctions spécifiques.

| Fonctionnalités | Sources de données |
| --- | --- |
| Recherche et métadonnées | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Notes complémentaires | [IMDb](https://www.imdb.com/) |
| Recherche par image | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Épisodes, génériques et plages | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) fournit les correspondances d'ID entre services. La source de plages SkipDB est actuellement désactivée ; une source répertoriée ne garantit pas la couverture de tous les titres ou épisodes.

## Démarrage rapide

Nécessite Python 3.11–3.14 sous Linux, macOS ou Windows. Clonez le dépôt et utilisez le lanceur multiplateforme :

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# Renseigner BOT_TOKEN dans .env.d/telegram.env
python3 scripts/project.py check
python3 scripts/project.py run
```

Sous Windows, utilisez `py -3 scripts\project.py` à la place de `python3 scripts/project.py`. Le lancement en arrière-plan utilise `python3 scripts/project.py start` (ainsi que `status`, `restart`, `stop`) ; sous Linux, `./start.sh` est aussi disponible.

## Utilisation

`/anime` permet de choisir une source ou de saisir un titre. Une image jointe à `/anime` ou une URL d'image publique lance la recherche inversée si un service est disponible. `/settings` gère les préférences et `/cancel` annule la saisie.

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

`BOT_TOKEN` est obligatoire. Les autres identifiants sont facultatifs : `MAL_CLIENT_ID` étend MyAnimeList et `ANIDB_CLIENT` active AniDB. La recherche par image accepte le mode invité. Les profils proxy et User-Agent résident dans `.proxies.d/` et `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Le bot télécharge et vérifie les versions d'**Anime Mapping DB**, puis lit `mappings.db` directement. Il ne construit pas les correspondances et ne dépend pas d'**Anime Timestamp DB**.

## Documentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Licence et attribution

Le code est sous Apache-2.0. Les données et services tiers conservent leurs licences, leurs obligations de citation et leurs conditions d'API. Ne validez jamais d'identifiants secrets. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
