> **Projet assisté par l'IA :** Ce projet a été développé avec l'aide de l'IA.

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <strong>Français</strong> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

> Recherche d'anime Telegram native et agrégation de métadonnées sur MyAnimeList/Jikan, AniList, Shikimori, Kitsu, AniDB et AniSearch.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` recherche plusieurs bases de données d'anime, résout les identités croisées confirmées et crée une carte indépendante de la source sans traiter aucune base de données externe comme source canonique de vérité.

Le projet est conçu autour de limites explicites entre la **recherche**, l'**identité**, les **mappings**, les **sources de métadonnées**, l'**agrégation**, la **localisation** et l'**interface utilisateur de la plateforme**. Les gens utilisent un manifeste léger d'identification/nom/rôle préextrait pour les totaux exacts, tandis que les portraits sont enrichis en lots globaux délimités ; d'autres données coûteuses telles que les personnages, les bandes-annonces et les épisodes restent lazy.

## Points forts

- **Recherche multi-fournisseurs** — Shikimori, MyAnimeList, AniList et Kitsu sont interrogés via un flux `/anime`.
- **Identité indépendante de la source** — `AnimeIdentity` stocke les identifiants externes des homologues ; il n’existe pas d’ID de base de données principale globale.
- **Mappage conservateur d'ID croisés** : le mappage d'exécution est direct uniquement et tient compte des conflits, avec des remplacements de provenance et d'audit manuels.
- **Cartes de métadonnées agrégées** : les valeurs des sources de métadonnées réussies sont normalisées et fusionnées tandis que la provenance spécifique à la source est préservée.
- **Manifeste + enrichissement lazy** — les identifiants, noms et rôles du personnel/seiyuu sont préextraits sous la forme d'une liste exacte et légère ; les portraits sont enrichis par lots globaux (50 par défaut), tandis que les personnages, les captures d'écran, la popularité détaillée, les descriptions/arrière-plans, les bandes-annonces et les épisodes restent lazy.
- **Couche de résilience partagée** : erreurs de source typées, tentatives, disjoncteurs, récupération semi-ouverte, limites de débit et cycle de vie partagé HTTP.
- **Paramètres persistants au niveau de la plate-forme** : les paramètres régionaux de l'utilisateur, les utilisateurs connus et l'état de modération sont stockés dans SQLite.
- **Sept langues de l'interface utilisateur** — L'anglais est la langue par défaut/de secours ; Le russe, le japonais, l'allemand, l'espagnol, le français et l'italien sont entièrement sélectionnables en `/settings`.
- **Vérifications orientées production** — Python 3.11–3.14 CI, Ruff, vérifications du formateur, portée mypy, porte de couverture et ShellCheck.

## Capacités sources

| Source | Rechercher | Métadonnées | Personnes | Personnages | Bandes-annonces | Épisodes | Captures d'écran | Popularité | Descriptif |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu est une source JSON:API publique native à l'identité. Les requêtes GET publiques en lecture seule ne nécessitent pas d'informations d'identification OAuth ; Les identifiants Kitsu confirmés participent déjà à `mappings.db`, et Kitsu peuvent également renvoyer des mappages directs MAL/AniList/AniDB avec les résultats de recherche et les métadonnées. Kitsu contribue actuellement à la recherche, aux métadonnées, à la popularité, aux descriptions, aux épisodes et à une bande-annonce YouTube lorsqu'elle est disponible. Les personnes/personnages ne sont intentionnellement pas annoncés car ces relations sont souvent rares.

AniDB est facultatif et n'est activé que lorsque `ANIDB_CLIENT` est configuré. Jikan n'est **pas** une base de données d'identité distincte : il s'agit d'un backend MAL local utilisé pour les données qui ne sont pas disponibles via le MAL officiel API. Ses concédants de licence de carte principale et ses statistiques de popularité lazy utilisent des points de terminaison locaux distincts, de sorte que le grattage de la distribution des scores ne figure pas sur le chemin initial de la carte. AniSearch est une source de base de données d'identité native API résolue via des bords de mappage `anisearch` confirmés. Son public API n'expose pas la recherche normale par requête de titre, il ne rejoint donc pas le chemin de recherche rapide `/anime <title>`. Parce que AniSearch place ID et `/full` dans le même groupe de limitation strict, la source effectue une récupération `/full` en cache par titre et garde les champs lourds hors de l'agrégation initiale ; les personnes, les personnages et les épisodes réutilisent ensuite cette même charge utile sans autre attente sur le réseau. Les localisations en anglais, japonais, allemand, espagnol, français et italien AniSearch sont utilisées pour les titres/synonymes localisés, les synopsis, les titres d'épisodes, les concédants de licence régionaux et les crédits vocaux. Les demandes publiques sans jeton sont rythmées selon l'intervalle de famille d'identification documenté de 10 secondes (5 secondes avec un jeton valide), et le texte de synthèse provenant de la source AniSearch conserve le lien d'attribution direct AniSearch requis. Le support SkipDB reste dans la base de code en tant que fournisseur dormant soutenu par IMDb, mais il n'est intentionnellement pas enregistré dans le runtime car la couverture actuelle des segments de saut d'anime est trop petite pour justifier son exposition dans l'interface utilisateur. Son analyseur/paramètres/tests sont conservés afin qu'il puisse être réactivé ultérieurement si la couverture s'améliore. Les données SkipDB sont servies sous ODbL 1.0 + réciprocité.

## Comment ça marche

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

### Règles d'identité

`AnimeIdentity` n'a pas d'identifiant principal. Un identifiant numérique provenant d'une base de données n'est jamais censé identifier le même titre dans une autre base de données simplement parce que le numéro correspond.

La fusion inter-sources suit des règles conservatrices :

1. les identifiants externes partagés explicites constituent une preuve d’identité solide ;
2. des identifiants conflictuels provenant du même fournisseur empêchent une fusion ;
3. la recherche de texte peut utiliser une solution de repli romaji normalisée exacte et contrainte uniquement lorsqu'il n'existe aucun conflit entre le même fournisseur ;
4. La recherche par ID direct n'utilise **pas** la fusion de titres uniquement ;
5. les mappages d'exécution sont directs uniquement et ne traversent pas de manière récursive des chaînes arbitraires de style TVDB/TMDB.

L’identité entièrement enrichie reste disponible en interne pour les fonctionnalités de routage et les capacités lazy. Le bloc d'identification visible de la carte affiche uniquement les identifiants appartenant aux sources de métadonnées qui ont réellement contribué à cette carte.

## Recherche

La seule commande de recherche destinée à l'utilisateur est `/anime`.

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
/anime kitsu:<id>
```

`/anime <title>` interroge tous les moteurs de recherche enregistrés en parallèle et collecte un ensemble de résultats limités à l'échelle de la requête avant la pagination Telegram. La pertinence prend en compte les titres, les alias, les variantes natives/romaji, les correspondances jeton/préfixe, la translittération et une solution de repli conservatrice en matière de similarité.

Les majuscules de pages/éléments protègent les quotas en amont. Lorsque le robot ne peut pas prouver que le décompte collecté est définitif, l’interface utilisateur signale un décompte incomplet au lieu de le présenter comme exact.

L'exécution de `/anime` sans arguments ouvre un sélecteur de source interactif. Les entrées en attente sont limitées à la paire utilisateur/chat, expirent automatiquement et peuvent être annulées avec `/cancel`.

`/anime` prend également en charge la recherche d'images inversée. Attachez une image à la commande ou transmettez une URL d'image publique et le bot propose uniquement des backends de recherche d'images dont le quota est actuellement disponible : trace.moe, What Anime Is This ou les deux. Les résultats sont résolus via AniList ID confirmés et affichés comme aperçu du candidat paginé normal ; la carte de métadonnées complète n'est ouverte qu'une fois que l'utilisateur a choisi **Détails**. Les preuves de correspondance (fournisseur, similarité, épisode, horodatage) sont conservées dans l'aperçu. L'action **Pas le titre dont vous avez besoin ?** permet une autre tentative de source ou une annulation sans contourner les quotas du fournisseur. Les images raster téléchargées sont normalisées au format JPEG avant la recherche sortante.

Les informations d’identification de recherche d’images sont facultatives. trace.moe s'exécute de manière anonyme lorsque `TRACE_MOE_API_KEY` est vide et lit le quota actuel réel à partir de `/me` ; les clés configurées sont envoyées sous la forme `x-trace-key`, de sorte que les quotas de partenaires/donateurs sont découverts plutôt que codés en dur. What Anime Is This s'exécute en tant qu'invité lorsque `WHATANIMEISTHIS_API_KEY` est vide et utilise `Authorization: Bearer ...` lorsqu'une clé est présente. Étant donné que son API public n'expose pas l'état de crédit de la clé API, le bot maintient un compteur quotidien local persistant conservateur : les valeurs par défaut sont 5 recherches d'invités et 10 recherches de clé API, et les deux plafonds sont configurables pour les comptes avec des politiques de crédit différentes. Définissez `WHATANIMEISTHIS_API_DAILY_LIMIT=0` pour désactiver le plafond local de API et comptez sur les propres erreurs de crédit/quota du service. Une réponse de quota côté serveur marque immédiatement ce backend indisponible pour la période de quota local en cours.

## Sections lazy de la carte

La carte principale reste axée sur les métadonnées. Les sections suivantes sont chargées uniquement sur demande :

- le personnel et les créateurs ;
- des acteurs vocaux, y compris des crédits de doublage étiquetés dans la langue AniSearch ;
- personnages et portraits;
- captures d'écran ;
- distributions détaillées de popularité/classement ;
- descriptions et texte d'arrière-plan source ;
- bandes-annonces/promotions ;
- épisodes.

Les crédits vocaux japonais restent la base de référence en langue originale non étiquetée. AniSearch les crédits de doublage sont conservés avec les suffixes de rôle explicites `[EN]`, `[DE]`, `[ES]`, `[FR]` ou `[IT]` afin qu'ils ne se fassent jamais passer pour des crédits japonais originaux. Le personnel de localisation/ADR est exclu de la liste du personnel de production primaire.

## Exigences et prise en charge de la plateforme

Le runtime Python est conçu pour **Linux, macOS et natif Windows** avec Python **3.11, 3.12, 3.13 ou 3.14**. GitHub Actions exécute la suite complète d'unités sur les trois familles de systèmes d'exploitation pour chaque version Python prise en charge.

- **Linux** — plateforme de production primaire ; le lanceur multiplateforme fonctionne sur les distributions grand public tant qu'une version CPython prise en charge est disponible. Le `start.sh` fourni reste un assistant de production `tmux` orienté Linux.
- **macOS** — pris en charge via le lanceur Python ; `start.command` est fourni comme emballage pratique. Les unités de maintenance `systemd` ne s'appliquent pas sur macOS.
- **Windows (natif)** — pris en charge via le lanceur Python, `start.ps1` ou `start.cmd` ; WSL n’est pas requis.
- **Docker + Docker Compose** — facultatif sur chaque plateforme et utilisé uniquement pour le supplément local Jikan. Le bot fonctionne toujours sans Docker ; Le MAL officiel reste disponible tandis que les fonctionnalités supplémentaires uniquement Jikan sont désactivées.
- **systemd** — intégration facultative de déploiement/maintenance Linux uniquement sous `deploy/systemd/`.

Exécutez `python scripts/project.py doctor` (ou la même commande avec votre interpréteur Python actif) pour vérifier la compatibilité de base d'exécution/dépendance d'une machine.

## Démarrage rapide

Clonez d'abord le dépôt :

```text
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Le lanceur canonique est `scripts/project.py`. Il crée `.venv`, installe les dépendances verrouillées, crée les répertoires de configuration manquants à partir des exemples validés sans écraser les valeurs existantes et comprend la disposition native de l'environnement virtuel sous Unix et Windows.

Linux / macOS :

```bash
python3 scripts/project.py setup
# Edit .env.d/telegram.env and add at least BOT_TOKEN.
python3 scripts/project.py check
python3 scripts/project.py run       # foreground
python3 scripts/project.py start     # background + PID file
```

Windows PowerShell / Invite de commandes :

```powershell
py -3 scripts\project.py setup
# Edit .env.d\telegram.env and add at least BOT_TOKEN.
py -3 scripts\project.py check
py -3 scripts\project.py run
.\start.ps1                         # background
```

`start.cmd` est disponible pour l'invite de commande et macOS peut utiliser `./start.command`. Les processus en arrière-plan démarrés par le lanceur multiplateforme sont gérés avec :

```text
python scripts/project.py status
python scripts/project.py stop
python scripts/project.py restart
```

Linux les déploiements de production peuvent continuer à utiliser `./start.sh` ; il préserve le flux de travail détaché `tmux` existant. Les journaux d'exécution restent sous `logs/YYYY.MM.DD/`, tandis que le lanceur générique en arrière-plan écrit également sa sortie stdout/stderr héritée dans `logs/launcher.log`.

Les journaux d'exécution sont répartis par responsabilité sous `logs/YYYY.MM.DD/` : `bot.log` contient les événements d'application/d'exécution, `users.log` contient Telegram le suivi des actions de l'utilisateur, `api.log` contient les événements source/API/nouvelle tentative/santé sortants et `errors.log` duplique tous les `ERROR+` enregistrements pour des diagnostics rapides. Le répertoire change automatiquement après minuit local sans redémarrer le bot.

## Configuration

Toute l'analyse de l'environnement d'exécution est centralisée dans `core/settings.py`. Les nouveaux déploiements copient `.env.example.d/` vers `.env.d/`. Seuls les fichiers corrigés `telegram.env`, `sources.env`, `timestamps.env`, `rate-limits.env`, `mappings.env`, `storage.env`, `logging.env` et `runtime.env` sont chargés ; les fichiers parasites tels que `backup.env` sont ignorés. Les clés en double dans les fichiers de configuration du projet échouent au démarrage, tandis que les variables d'environnement de processus réelles ont la priorité la plus élevée. Un `.env` monolithique reste pris en charge uniquement comme chemin de migration.

### Paramètres essentiels

| Variables | Obligatoire | Objectif |
| --- | :---: | --- |
| `BOT_TOKEN` | Oui | Telegram jeton de bot de BotFather. |
| `MAL_CLIENT_ID` | Recommandé | Active la recherche et les métadonnées officielles MyAnimeList. |
| `ANIDB_CLIENT` | Non | Active AniDB HTTP API métadonnées/personnes/épisodes. |
| `ANIDB_CLIENT_VERSION` | Non | Version client enregistrée AniDB HTTP API ; la valeur par défaut est `1`. |
| `ANILIST_ACCESS_TOKEN` | Non | Jeton AniList facultatif lorsqu’un accès authentifié est souhaité. |
| `KITSU_API_URL` | Non | Kitsu public JSON:API URL de base ; la valeur par défaut est `https://kitsu.io/api/edge`. |
| `TRACE_MOE_API_KEY` | Non | Touche facultative trace.moe API (`x-trace-key`) ; le mode libre fonctionne sans cela et le quota est lu à partir de `/me`. |
| `WHATANIMEISTHIS_API_KEY` | Non | Clé facultative What Anime Is This API envoyée sous la forme `Authorization: Bearer ...` ; le mode invité gratuit fonctionne sans lui. |
| `IMAGE_SEARCH_DB_PATH` | Non | SQLite chemin pour une comptabilité conservatrice des quotas de recherche d'images persistantes. |
| `ADMIN_TELEGRAM_USER_IDS` | Non | ID utilisateur administrateur Telegram séparés par des virgules/espaces/points-virgules. |
| `TELEGRAM_BOT_API_URL` | Non | Point de terminaison Telegram Bot API personnalisé/auto-hébergé. |
| `TELEGRAM_BOT_API_LOCAL_FILE_ROOT` | Non | Répertoire hôte mappé sur `/var/lib/telegram-bot-api` lorsque les chemins de fichiers locaux du Bot API se trouvent à l'intérieur d'un conteneur. |
| `USER_SETTINGS_DB_PATH` | Non | SQLite chemin pour les paramètres par utilisateur et le registre des utilisateurs connus. |
| `BANS_DB_PATH` | Non | SQLite chemin pour les interdictions de modération. |
| `MAPPINGS_DB_PATH` | Non | Base de données de mappage d'ID croisés d'exécution. |

Ne validez pas `.env`, `.env.d/`, `.proxies.d/`, les jetons de bot, les jetons d'accès, les mots de passe, les informations d'identification de proxy ou les informations d'identification privées API.

### Pools de proxy par source

Le routage proxy sortant facultatif est configuré séparément sous `.proxies.d/`, un fichier TOML fixe par source d'exécution plus `telegram.toml` pour le bot lui-même. Commencez à partir de `.proxies.example.d/`. Les schémas de proxy pris en charge sont `http`, `socks4` et `socks5`.

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

Les profils sont indépendants : `mal.toml` n'affecte que MAL, `anilist.toml` uniquement AniList, et ainsi de suite. Les valeurs `priority` plus élevées sont essayées avant les valeurs inférieures, quel que soit l'ordre TOML. Les inscriptions à égalité avec la même priorité sont sélectionnées à la ronde ; Les niveaux de priorité inférieure sont utilisés uniquement comme basculement après la défaillance du niveau supérieur. Les URL de proxy en double sont autorisées lorsqu'elles ont des noms d'entrée distincts. Par conséquent, la répétition d'un point de terminaison peut intentionnellement lui donner plus de poids de rotation. `enabled = false` peut désactiver soit l'ensemble du profil, soit une entrée individuelle. Si au moins une entrée de proxy est active pour un profil, ce profil ne revient **pas** silencieusement à la connexion directe lorsque tous les proxys échouent ; l'accès direct est utilisé uniquement lorsque le profil n'a pas de proxy actif. La configuration du proxy est chargée au démarrage du processus, donc les modifications prennent effet après le redémarrage du robot. Lorsque `telegram.toml` a des proxys actifs, ce bot contourne intentionnellement tout point de terminaison local/partagé `telegram-bot-api` configuré et parle au `api.telegram.org` officiel via son propre pool de proxy ; cela maintient le proxy limité à ce bot au lieu de modifier les autres robots qui partagent le serveur local. `jikan.toml` est également spécial : le saut Python vers le service de bouclage Jikan reste direct, tandis que le proxy sélectionné est transmis au service Jikan local et appliqué à son scrape sortant MyAnimeList.

Les profils d'exécution fixes sont : `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `bahamut`, `baha_anime_skip`, `skipdb`, `trace_moe` et `whatanimeisthis`. Les fichiers TOML parasites sont ignorés. Les fichiers proxy peuvent contenir des informations d'identification et sont ignorés par git ; `start.sh` conserve `.proxies.d` en mode `700` et les fichiers de profil connus en mode `600`.

### Profils d'agent utilisateur par source

Les remplacements facultatifs d'agent utilisateur se trouvent sous `.user-agents.d/` avec les mêmes noms de profil fixes que le routage proxy. Si un profil n'a pas d'entrée personnalisée active, les requêtes utilisent l'agent utilisateur du projet intégré (`anime-db-bot/<version> (...)`). Des victoires `priority` plus élevées ; les entrées liées à la priorité active la plus élevée alternent entre les demandes. Les agents utilisateurs de priorité inférieure restent en veille jusqu'à ce que les entrées de priorité supérieure soient désactivées.

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

La limite du réseau remplace les en-têtes `User-Agent` locaux du fournisseur afin que la valeur du profil sélectionnée fasse autorité. Pour `jikan`, l'agent utilisateur sélectionné est transmis via le service de bouclage et appliqué à sa requête sortante MyAnimeList. Pour `telegram`, un agent utilisateur personnalisé actif fait passer ce bot d'un point de terminaison partagé/local `telegram-bot-api` au point de terminaison officiel `api.telegram.org`, garantissant que l'en-tête configuré atteint la requête externe Telegram. `.user-agents.d` est gitignoré et chargé au démarrage du processus.

### AniDB

L'intégration utilise les AniDB HTTP API. Il nécessite un HTTP API **nom et version du client** enregistrés, et non un AniDB mot de passe de compte.

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

Les réponses XML AniDB sont mises en cache sur le disque et les requêtes réseau sont sérialisées avec un intervalle de requête minimum supplémentaire pour respecter les attentes API du service.

### MAL / Jikan

MAL est la source d'identité. Jikan est un backend supplémentaire local et n'introduit jamais de clé d'identité `jikan`.

Le service groupé réside sous :

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Une panne Jikan ne rend pas la recherche/métadonnées officielles MAL indisponibles.

## Commandes

### Commandes utilisateur

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

### Commandes d'administration

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

Les mutations cartographiques se déroulent intentionnellement en deux étapes. `/mapping_set` et `/mapping_delete` créent une mutation en attente de courte durée ; la base de données ne change qu'après le `/mapping_confirm <token>`. L'historique d'audit enregistre l'administrateur Telegram responsable du changement.

## Localisation

Le modèle de domaine est neutre en termes de paramètres régionaux. Les adaptateurs sources normalisent les valeurs de statut/type/saison/genre/rôle en amont en clés canoniques, et la traduction n'a lieu qu'au moment du rendu.

Paramètres régionaux de l'interface utilisateur pris en charge :

- `en` — Anglais (**par défaut et solution de secours**) ;
- `ru` — Russe ;
- `ja` — 日本語;
- `de` — Allemand ;
- `es` — Español ;
- `fr` — Français ;
- `it` — Italien.

Les utilisateurs existants conservent leurs paramètres régionaux explicitement enregistrés. Les nouveaux utilisateurs, les paramètres manquants, les valeurs de paramètres régionaux non valides et les clés de traduction manquantes reviennent à l'anglais.

Le texte source de forme libre tel que les descriptions d’anime n’est pas traduit automatiquement. Voir [`localization/README.md`](../localization/README.md) pour l'architecture de localisation et les règles de maintenance.

## Persistance

Le runtime sépare les différents types d’état :

- paramètres utilisateur et utilisateurs connus — SQLite, limité à `(platform, user_id)` ;
- interdictions — magasin SQLite persistant séparé ;
- `mappings.db` — base de données de résolution d'ID croisés sauvegardée sur disque ;
- AniDB XML — cache disque ;
- Telegram sessions de recherche/rappel de carte — état TTL/LRU en mémoire limité.

Les paramètres utilisateur hérités créés avant la portée de la plate-forme sont migrés en tant qu'enregistrements Telegram sans modifier leurs paramètres régionaux enregistrés.

## Résilience et limitation de débit

Le trafic sortant HTTP utilise des instances partagées `httpx.AsyncClient` appartenant à `AppContext`. Les pannes de source sont normalisées en erreurs typées et transmises via une couche commune de nouvelle tentative/disjoncteur.

Le registre de santé source prend en charge :

- gestion des pannes transitoires et non transitoires ;
- tentatives limitées avec interruption ;
- seuils de disjoncteur ;
- temps de recharge ;
- exactement une sonde de récupération entrouverte.

Les limites personnelles Telegram sont limitées à `(platform, user_id)`. Les administrateurs peuvent contourner le limiteur personnel, mais **jamais** contourner les limites de sécurité du fournisseur en amont.

## Architecture

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

`services/runtime/app_context.py` est la racine de la composition de l'application. Les dépendances d'exécution de production doivent y être détenues plutôt que créées en tant que singletons de service au moment de l'importation.

Plus de détails : [`docs/app-context.md`](app-context.md).

## Mappages d’ID croisés

Le programme de mise à jour de cartographie diffuse plusieurs ensembles de données externes dans SQLite, enregistre la provenance/les preuves/les conflits, valide la base de données reconstruite et la met en place de manière atomique. Le graphique complet n'est pas chargé dans la RAM.

Les remplacements directionnels manuels prennent en charge `accept` et `reject`, transportent les métadonnées d'auteur/raison/horodatage et préservent l'historique des ajouts uniquement lors des reconstructions.

Les commandes de maintenance sont disponibles via le lanceur multiplateforme :

```text
python scripts/project.py mappings --status
python scripts/project.py mappings --override-list
python scripts/project.py mappings --override-history
```

Le wrapper Unix `./scripts/update-mappings.sh` reste disponible pour les déploiements existants.

## Développement

Utilisez le même lanceur sur tous les systèmes d'exploitation pris en charge :

```text
python scripts/project.py setup --dev
python scripts/project.py check
python scripts/project.py doctor
```

Le Windows, `py -3 scripts\project.py ...` peut être utilisé à la place de `python`. Les fichiers Unix `./scripts/setup.sh` et `./scripts/check.sh` sont des wrappers pratiques autour de la même implémentation. Les commandes directes d'environnement virtuel restent disponibles en `.venv/bin/python` sous Unix et en `.venv\Scripts\python.exe` en Windows.

GitHub Actions nécessite que la suite d'unités complète transmette **Ubuntu, macOS et Windows** pour Python 3.11, 3.12, 3.13 et 3.14. Chaque tâche matricielle exécute également le lanceur multiplateforme Doctor. Le travail de qualité Linux exécute en outre Ruff vérifications d'exactitude, des vérifications du formateur pour la fondation typée, mypy pour la fondation typée, des tests complets avec une porte de couverture d'au moins 70 % et ShellCheck pour les wrappers de shell Unix.

## Contribuer

Les contributions sont les bienvenues. Lisez [CONTRIBUTING.md](../CONTRIBUTING.md) avant d'ouvrir une pull request et suivez le projet [Code of Conduct](../CODE_OF_CONDUCT.md). Les rapports de bogues et les demandes de fonctionnalités doivent utiliser les formulaires de problème du référentiel.

## Sécurité

- Conservez `.env` et les informations d'identification en dehors du contrôle de version.
- Les journaux utilisent des fichiers `bot/users/api/errors` quotidiens, une rédaction secrète par défaut, des ID de corrélation par mise à jour, des horodatages de fuseau horaire local à l'exécution et une rotation limitée par fichier. `LOG_REDACT_SECRETS=0` désactive délibérément tout masquage pour les diagnostics locaux et peut écrire les informations d'identification textuellement ; gardez-le activé sur les journaux partagés/publics.
- Les actions réservées à l'administrateur doivent rester derrière la couche de contrôle d'accès.
- N'exposez pas publiquement un robot Telegram auto-hébergé API, un futur point de terminaison de métriques ou un futur API externe sans contrôles d'authentification/réseau explicites.
- Les remplacements de mappage sont audités, car une limite d'identité incorrecte peut affecter plusieurs fonctionnalités.

Pour les rapports de vulnérabilité et les canaux de sécurité pris en charge, voir [SECURITY.md](../SECURITY.md). Ne publiez pas d’informations d’identification, de jetons ou de détails de déploiement privé dans un numéro public.

## Statut du projet

Le projet est en développement actif. Le flux de recherche/carte de base Telegram, le modèle d'identité, la base de données de cartographie, l'agrégation multi-sources, la localisation, les capacités lazy, la persistance, la résilience et la base CI sont mis en œuvre. Des filtres de découverte/recherche supplémentaires, des intégrations de comptes d'utilisateurs, des notifications, des mesures de surveillance/Prometheus, la prise en charge externe de API/Mini App et d'autres sources sont des travaux prévus.

## Licence

Sous licence [Apache License 2.0](../LICENSE). Vous pouvez utiliser, modifier et distribuer le projet selon ses conditions ; conserver les avis requis et marquer les modifications importantes requises par la licence.

## Sources de données et remerciements

`anime-db-bot` s'intègre ou s'appuie sur les données de projets et de services, notamment :

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Kitsu](https://kitsu.app/) — public en lecture seule JSON:API ; aucun OAuth requis pour les requêtes GET normales
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) — Métadonnées de la base de données API ; les exigences d'attribution et de lien de synthèse s'appliquent
- [SkipDB](https://skipdb.tv/) — données de segment ignoré sous ODbL 1.0 + réciprocité

Les données de cartographie Cross-ID sont assemblées à partir de plusieurs ensembles de données communautaires. Chaque service et ensemble de données en amont reste soumis à ses propres conditions, limites de débit et exigences d'attribution.

Kitsu Les requêtes GET publiques en lecture seule sont utilisées sans OAuth informations d'identification. Le moteur d'exécution applique ses propres limites de requêtes prudentes, car aucun contrat de limite de débit stable côté serveur n'est supposé.

AniSearch Base de données API Les requêtes de métadonnées en lecture seule ne nécessitent pas OAuth. `ANISEARCH_APP_ID` et `ANISEARCH_APP_SECRET` sont des informations d'identification d'application OAuth facultatives réservées aux futures fonctionnalités AniSearch autorisées par l'utilisateur ; ils ne sont jamais envoyés avec des requêtes de base de données en lecture seule.
