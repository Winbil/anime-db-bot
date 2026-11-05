> **Proyecto desarrollado con ayuda de IA.**

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <strong>Español</strong> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

Bot de Telegram para buscar anime en bases independientes y reunir fichas, episodios, personajes, personal de producción y obras relacionadas en una sola interfaz.

## Funciones

- Búsqueda por título, ID externo o imagen, con resultados paginados.
- Valoraciones, sinopsis, emisión, reparto, personal, relaciones y recomendaciones agregados.
- Episodios, información de OP/ED e intervalos de salto disponibles, cargados al abrir cada sección.
- Identidad conservadora: solo se unen títulos mediante correspondencias de ID verificadas.
- Preferencias persistentes, moderación, límites por fuente y perfiles de proxy y User-Agent.
- Interfaz en siete idiomas, respetando los idiomas del contenido original.

## Búsqueda y navegación

`/anime` recibe títulos o IDs explícitos de proveedores. Primero muestra resultados paginados y luego una ficha detallada. Reconoce nombres y alias de distintas escrituras, pero una consulta por ID nunca une títulos solo por similitud textual.

La búsqueda inversa acepta imágenes de Telegram o URLs públicas. Los proveedores disponibles muestran similitud, episodio y marca temporal antes de abrir la ficha. Se respetan los cupos de invitado y de API de cada servicio.

La ficha principal contiene información normalizada. Personal, actores de voz, personajes, imágenes, estadísticas detalladas, sinopsis, tráilers, títulos relacionados, recomendaciones y episodios se cargan al abrirlos. Temporadas y especiales solo se muestran cuando la fuente aporta dicha estructura.

## Fuentes de datos

Los metadatos provienen de MyAnimeList (con Jikan como complemento), AniList, Shikimori, Kitsu, AniDB (registro de cliente opcional) y AniSearch. Otros servicios aportan funciones concretas.

| Funciones | Fuentes de datos |
| --- | --- |
| Búsqueda y metadatos | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Valoraciones adicionales | [IMDb](https://www.imdb.com/) |
| Búsqueda por imagen | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Episodios, temas e intervalos | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) proporciona las correspondencias entre IDs de servicios. El proveedor de intervalos SkipDB está desactivado; enumerar una fuente no garantiza datos para todos los títulos o episodios.

## Capacidades por fuente

| Fuente | Búsqueda | Metadatos | Equipo | Personajes | Episodios | Relaciones | Recomendaciones |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch aporta información localizada y voces de doblaje a títulos confirmados, sin realizar la búsqueda normal por nombre. AnimeThemes añade OP/ED a los episodios. SkipDB está actualmente inactivo como proveedor runtime.

## Identidad y agregación

Ningún catálogo externo se considera autoridad universal. Los IDs de MAL, AniList, Shikimori, Kitsu, AniDB y AniSearch se relacionan solo con pruebas confirmadas. Un número igual, un título similar o una franquicia compartida no bastan.

La resolución es directa y detecta conflictos. La agregación mantiene la procedencia de cada valor y las vistas específicas cuando existen. IMDb requiere una relación inequívoca con un ID nativo de anime; TVDB/TMDB por sí solos no sirven.

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

## Inicio rápido

Requiere Python 3.11–3.14 y Linux, macOS o Windows. Clone el proyecto y use el iniciador multiplataforma:

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# Configure BOT_TOKEN en .env.d/telegram.env
python3 scripts/project.py check
python3 scripts/project.py run
```

En Windows, utilice `py -3 scripts\project.py` en lugar de `python3 scripts/project.py`. Para ejecutarlo en segundo plano, use `python3 scripts/project.py start` (también admite `status`, `restart`, `stop`); Linux ofrece `./start.sh`.

## Despliegue y operación

El iniciador multiplataforma gestiona entorno virtual, verificaciones y procesos. Linux incluye `start.sh` con tmux, Windows `start.ps1`/`start.cmd` y macOS `start.command`.

Docker Compose y Jikan local son complementos opcionales. La API oficial de MAL sigue disponible sin Jikan. Las unidades `systemd` de `deploy/systemd/` son específicas de Linux.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

## Uso

`/anime` permite elegir una fuente o buscar por título. Una imagen adjunta a `/anime` o su URL pública activa la búsqueda inversa cuando haya un proveedor disponible. `/settings` cambia preferencias y `/cancel` cancela la entrada.

```text
/anime Frieren
/anime mal:5114
/anime anilist:<id>
/anime shikimori:<id>
/settings
/ping
/cancel
```

## Comandos de Telegram

`/anime` es la entrada habitual. Los comandos administrativos exigen IDs autorizados de Telegram; los cambios de mapping tienen confirmación y registro de auditoría.

| Comando | Función |
| --- | --- |
| `/start`, `/ping` | Iniciar y verificar disponibilidad |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | Buscar por título, ID o imagen |
| `/settings` | Idioma y preferencias |
| `/cancel` | Cancelar la entrada pendiente |
| `/users`, `/status`, `/source_health` | Usuarios, estado del bot y de las fuentes |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | Bloquear o desbloquear usuarios |
| `/mapping_overrides`, `/mapping_history [limit]` | Consultar excepciones e historial |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | Preparar, confirmar o cancelar cambios |

## Configuración

Se requiere `BOT_TOKEN`. Las demás credenciales son opcionales: `MAL_CLIENT_ID` amplía MyAnimeList y `ANIDB_CLIENT` activa AniDB. La búsqueda de imágenes admite modo invitado. Los perfiles de proxy y User-Agent están en `.proxies.d/` y `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

El bot descarga y verifica las versiones de **Anime Mapping DB**, consultando `mappings.db` directamente. No genera correspondencias ni depende de **Anime Timestamp DB**.

## Referencia de configuración

Las plantillas generan `.env.d/` sin sobrescribir valores. Solo se leen archivos de nombres previstos. Las variables de entorno del proceso tienen prioridad y los duplicados entre archivos impiden el inicio. Nunca guarde secretos en Git.

| Variable | Función |
| --- | --- |
| `BOT_TOKEN` | Token de Telegram obligatorio |
| `MAL_CLIENT_ID` | ID oficial de MyAnimeList |
| `ANIDB_CLIENT` | Cliente opcional para AniDB HTTP |
| `ANILIST_ACCESS_TOKEN` | Acceso autenticado opcional de AniList |
| `TRACE_MOE_API_KEY` | Clave trace.moe; modo invitado disponible |
| `WHATANIMEISTHIS_API_KEY` | Clave What Anime Is This; modo invitado |
| `ADMIN_TELEGRAM_USER_IDS` | IDs de administradores de Telegram |
| `TELEGRAM_BOT_API_URL` | Servidor Telegram Bot API propio |
| `MAPPINGS_DB_PATH` | Ruta de la base de IDs |
| `IMDB_RATINGS_BACKEND` | Modalidad de valoraciones IMDb |
| `BAHA_ANIME_SKIP_DB_PATH` | Ruta del índice Baha |

Cada fuente dispone de un perfil TOML en `.proxies.d/` compatible con HTTP, SOCKS4 y SOCKS5. Las prioridades deciden orden y failover, las entradas empatadas rotan. Si fallan todos los proxies activos, no se cambia silenciosamente a conexión directa.

Los perfiles User-Agent se guardan en `.user-agents.d/`. Ambos se actualizan al reiniciar el proceso. Un servidor Telegram Bot API propio es opcional y debe protegerse.

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

Las variables y nombres admitidos se definen en `.env.example.d/`, `.proxies.example.d/` y `.user-agents.example.d/`.

## Datos locales y mantenimiento

El actualizador valida `mappings.db.zst` y sus hashes, reemplaza la base local de forma atómica y conserva las excepciones administrativas auditadas. El bot no requiere la base de evidencia para funcionar.

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

El índice local de IMDb contiene únicamente valoraciones de títulos verificados, no el volcado completo. Baha Anime Skip se consulta desde un índice local sin llamadas a Bahamut durante la ejecución. Ambos índices se pueden reconstruir por separado.

Preferencias, usuarios conocidos, moderación y determinadas cuotas se guardan en SQLite. Los registros diarios se organizan en `logs/YYYY.MM.DD/` como `bot.log`, `users.log`, `api.log` y `errors.log`; el iniciador añade `logs/launcher.log`.

## Episodios, OP/ED e intervalos

Las listas de episodios y los intervalos son capacidades independientes. Elegir un proveedor de episodios no determina cuál ofrece los tiempos: cada uno maneja IDs y ámbitos propios. Si no se demuestra la correspondencia, se prefiere ausencia de datos a un episodio equivocado.

AnimeThemes complementa los episodios con nombres OP/ED, canciones, artistas y enlaces a vídeo. Las fuentes de intervalos pueden ofrecer aperturas, cierres y resúmenes; los tiempos pueden diferir por numeración o edición. Un resultado de una fuente no representa un consenso general.

## Operación y diagnóstico

Si no aparece un título, compruebe el origen de la respuesta y las correspondencias confirmadas. Una clave opcional ausente o error individual no debería detener toda la búsqueda. `/status` muestra las estadísticas y `/source_health` los circuit breakers.

Ante errores de inicio, ejecute `doctor` y `check`, revise `logs/YYYY.MM.DD/errors.log` y compruebe `BOT_TOKEN`. Reinicie tras cambiar `.env.d/`, proxy o User-Agent. Verifique los mappings antes de reconstruir índices IMDb/Baha.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## Arquitectura y resiliencia

Búsqueda, identidad, adaptadores, agregación, traducción, persistencia e interfaz Telegram son módulos separados. Timeouts, reintentos, límites y circuit breakers aíslan fallos de proveedores.

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

## Desarrollo y seguridad

Las contribuciones deben mantener la prudencia en las relaciones de ID y evitar llamadas innecesarias en la ficha inicial. Ejecute las pruebas antes de un PR. Informe vulnerabilidades por el canal de seguridad sin publicar secretos.

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md) · [Code of Conduct](../CODE_OF_CONDUCT.md)

## Documentación

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Licencia y atribuciones

El código usa Apache-2.0. Los servicios y datasets externos conservan sus licencias, condiciones de atribución y de API. No incluya credenciales en los commits. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
