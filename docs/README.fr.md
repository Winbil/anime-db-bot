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

## Recherche et navigation

`/anime` accepte un titre ou un ID explicite de fournisseur. Les résultats sont paginés avant l'ouverture de la fiche détaillée. Plusieurs graphies et alias sont pris en compte, mais une recherche par ID ne fusionne jamais des œuvres sur le seul titre.

La recherche inversée accepte une image Telegram ou une URL publique. Les services disponibles indiquent similitude, épisode et horodatage avant l'ouverture de la fiche. Les quotas invités et authentifiés sont gérés par fournisseur.

La fiche principale présente les données normalisées. Personnel, comédiens, personnages, images, statistiques, descriptions, bandes-annonces, œuvres liées, recommandations et épisodes sont chargés à la demande. Les saisons et spéciaux ne sont regroupés que si la source fournit leur structure.

## Sources de données

Les métadonnées proviennent de MyAnimeList (Jikan en complément), AniList, Shikimori, Kitsu, AniDB (enregistrement client facultatif) et AniSearch. D'autres services sont utilisés pour des fonctions spécifiques.

| Fonctionnalités | Sources de données |
| --- | --- |
| Recherche et métadonnées | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Notes complémentaires | [IMDb](https://www.imdb.com/) |
| Recherche par image | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Épisodes, génériques et plages | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) fournit les correspondances d'ID entre services. La source de plages SkipDB est actuellement désactivée ; une source répertoriée ne garantit pas la couverture de tous les titres ou épisodes.

## Capacités des sources

| Source | Recherche | Métadonnées | Équipe | Personnages | Épisodes | Relations | Suggestions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch enrichit les titres identifiés avec des textes localisés et des voix de doublage sans participer à la recherche de titres. AnimeThemes fournit les génériques OP/ED par épisode. SkipDB n'est pas activé en runtime.

## Identité et agrégation

Aucune base d'anime n'est considérée comme référence universelle. Les identifiants MAL, AniList, Shikimori, Kitsu, AniDB et AniSearch ne sont rapprochés qu'avec des preuves confirmées. Numéro identique, titre semblable ou franchise commune ne suffisent pas.

La résolution se limite aux liens directs et vérifie les conflits. L'agrégation garde la provenance, avec vues par source lorsqu'elles existent. Les notes IMDb nécessitent une correspondance unique avec une source native d'anime ; une passerelle TVDB/TMDB seule ne suffit pas.

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

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

## Déploiement et exploitation

Le lanceur multiplateforme prépare l'environnement, vérifie l'installation et gère l'exécution. Linux dispose de `start.sh` et tmux, Windows de `start.ps1`/`start.cmd`, macOS de `start.command`.

Docker Compose et Jikan local sont facultatifs. L'API officielle de MAL reste utilisable sans Jikan. Les unités `systemd` dans `deploy/systemd/` sont réservées à Linux.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

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

## Commandes Telegram

`/anime` est l'entrée utilisateur principale. Les commandes administratives sont réservées aux ID Telegram autorisés ; les modifications de mappings exigent confirmation et sont historisées.

| Commande | Rôle |
| --- | --- |
| `/start`, `/ping` | Accueil et vérification |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | Recherche par titre, ID ou image |
| `/settings` | Langue et préférences |
| `/cancel` | Annuler une saisie |
| `/users`, `/status`, `/source_health` | Utilisateurs, état du bot et des sources |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | Bannir ou rétablir un utilisateur |
| `/mapping_overrides`, `/mapping_history [limit]` | Consulter les exceptions et l'historique |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | Préparer, confirmer ou annuler les changements |

## Configuration

`BOT_TOKEN` est obligatoire. Les autres identifiants sont facultatifs : `MAL_CLIENT_ID` étend MyAnimeList et `ANIDB_CLIENT` active AniDB. La recherche par image accepte le mode invité. Les profils proxy et User-Agent résident dans `.proxies.d/` et `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Le bot télécharge et vérifie les versions d'**Anime Mapping DB**, puis lit `mappings.db` directement. Il ne construit pas les correspondances et ne dépend pas d'**Anime Timestamp DB**.

## Référence de configuration

Les modèles alimentent `.env.d/` sans écraser les fichiers présents. Seuls les noms de fichiers prévus sont chargés. Les variables d'environnement du processus priment et les clés dupliquées entre fichiers provoquent une erreur. Ne conservez aucun secret dans Git.

| Variable | Rôle |
| --- | --- |
| `BOT_TOKEN` | Jeton Telegram requis |
| `MAL_CLIENT_ID` | ID du client MyAnimeList officiel |
| `ANIDB_CLIENT` | Client HTTP AniDB facultatif |
| `ANILIST_ACCESS_TOKEN` | Authentification AniList facultative |
| `TRACE_MOE_API_KEY` | Clé trace.moe, accès invité disponible |
| `WHATANIMEISTHIS_API_KEY` | Clé What Anime Is This, accès invité |
| `ADMIN_TELEGRAM_USER_IDS` | IDs Telegram autorisés à administrer |
| `TELEGRAM_BOT_API_URL` | Serveur Telegram Bot API personnalisé |
| `MAPPINGS_DB_PATH` | Chemin de la base d'identifiants |
| `IMDB_RATINGS_BACKEND` | Mode de notes IMDb |
| `BAHA_ANIME_SKIP_DB_PATH` | Chemin de l'index Baha |

Des profils TOML propres à chaque source sont possibles dans `.proxies.d/`, avec HTTP, SOCKS4 et SOCKS5. Priorités, rotation à priorité égale et bascule contrôlent les choix. Un profil actif en panne ne repasse pas silencieusement en direct.

Les profils User-Agent se configurent dans `.user-agents.d/`. Les changements prennent effet au redémarrage. Un serveur Telegram Bot API privé est facultatif et doit être protégé.

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

Les variables et noms de profils disponibles figurent dans `.env.example.d/`, `.proxies.example.d/` et `.user-agents.example.d/`.

## Données locales et maintenance

Le module de mise à jour vérifie `mappings.db.zst` et ses empreintes, remplace la base de façon atomique et conserve les exceptions administratives auditées. La base de preuves n'est pas nécessaire au bot.

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

L'index IMDb local retient uniquement les notes reliées à des identifiants d'anime confirmés, sans stocker le dump entier. Baha Anime Skip utilise aussi un index local sans requêtes Bahamut durant le runtime. Chaque index peut être reconstruit séparément.

Préférences, utilisateurs connus, modération et certains quotas sont enregistrés en SQLite. Les journaux quotidiens sous `logs/YYYY.MM.DD/` comprennent `bot.log`, `users.log`, `api.log`, `errors.log` et le lanceur écrit aussi `logs/launcher.log`.

## Épisodes, OP/ED et plages à ignorer

Les listes d'épisodes et les intervalles sont indépendants. Choisir un fournisseur d'épisodes n'impose pas un fournisseur de temps : chacun conserve ses IDs et sa numérotation. Une correspondance non prouvée reste absente plutôt que d'être associée au mauvais épisode.

AnimeThemes ajoute les noms OP/ED, musiques, artistes et liens vidéo aux vues d'épisodes. Les sources de plages fournissent génériques et récapitulatifs, parfois avec des horaires différents selon les versions et la numérotation. Une plage isolée n'est pas un consensus.

## Exploitation et diagnostic

Si un titre manque, vérifier la source qui a répondu et les correspondances confirmées. Un service défaillant ou une clé facultative manquante ne doit pas arrêter la recherche entière. `/status` expose les statistiques et `/source_health` les disjoncteurs.

En cas d'échec au démarrage, lancer `doctor` et `check`, consulter `logs/YYYY.MM.DD/errors.log` et vérifier `BOT_TOKEN`. Les changements de `.env.d/`, proxy ou User-Agent nécessitent un redémarrage. Vérifier les mappings avant de reconstruire les index IMDb/Baha.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## Architecture et résilience

Recherche, résolution d'ID, fournisseurs, agrégation, traduction, stockage et interface Telegram sont découplés. Délais d'attente, reprises, quotas et disjoncteurs limitent les défaillances externes.

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

## Développement et sécurité

Les contributions doivent préserver l'identité conservatrice et éviter des requêtes superflues à l'ouverture de la fiche. Exécutez les contrôles avant une PR. Signalez les vulnérabilités sans publier de secrets dans les issues.

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md) · [Code of Conduct](../CODE_OF_CONDUCT.md)

## Documentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Licence et attribution

Le code est sous Apache-2.0. Les données et services tiers conservent leurs licences, leurs obligations de citation et leurs conditions d'API. Ne validez jamais d'identifiants secrets. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
