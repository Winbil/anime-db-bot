> **Proyecto asistido por IA:** Este proyecto se desarrolló con la ayuda de IA.

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <strong>Español</strong> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

> Búsqueda de anime Telegram nativa de identidad y agregación de metadatos en MyAnimeList/Jikan, AniList, Shikimori, Kitsu, AniDB y AniSearch.

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` busca en múltiples bases de datos de anime, resuelve identidades confirmadas entre bases de datos y crea una tarjeta independiente de la fuente sin tratar ninguna base de datos externa como la fuente canónica de la verdad.

El proyecto está diseñado en torno a límites explícitos entre **búsqueda**, **identidad**, **asignaciones**, **fuentes de metadatos**, **agregación**, **localización** y **plataforma UI**. Las personas utilizan un manifiesto de ID/nombre/rol ligero y precargado para obtener totales exactos, mientras que los retratos se enriquecen en lotes globales acotados; otros datos costosos, como personajes, avances y episodios, permanecen flojos.

## Reflejos

- **Búsqueda de múltiples proveedores**: Shikimori, MyAnimeList, AniList y Kitsu se consultan a través de un flujo `/anime`.
- **Identidad independiente de la fuente**: `AnimeIdentity` almacena ID externos de pares; no hay ningún ID de base de datos principal global.
- **Mapeo conservador de ID cruzada**: el mapeo en tiempo de ejecución es solo directo y tiene en cuenta los conflictos, con anulaciones auditadas manuales y de procedencia.
- **Tarjetas de metadatos agregados**: los valores de fuentes de metadatos exitosas se normalizan y fusionan mientras se preserva la procedencia específica de la fuente.
- **Manifiesto + enriquecimiento diferido**: los ID, nombres y roles del personal/seiyuu se obtienen previamente como una lista exacta y liviana; los retratos se enriquecen en lotes globales (50 por defecto), mientras que los personajes, las capturas de pantalla, la popularidad detallada, las descripciones/fondos, los avances y los episodios siguen siendo vagos.
- **Capa de resiliencia compartida**: errores de origen escritos, reintentos, disyuntores, recuperación medio abierta, límites de velocidad y ciclo de vida compartido HTTP.
- **Configuraciones persistentes en el ámbito de la plataforma**: la configuración regional del usuario, los usuarios conocidos y el estado de moderación se almacenan en SQLite.
- **Siete idiomas de interfaz de usuario**: el inglés es la configuración regional predeterminada/alternativa; Ruso, japonés, alemán, español, francés e italiano se pueden seleccionar completamente en `/settings`.
- **Comprobaciones orientadas a la producción**: Python 3.11–3.14 CI, Ruff, comprobaciones del formateador, alcance mypy, puerta de cobertura y ShellCheck.

## Capacidades de origen

| Fuente | Buscar | Metadatos | Personas | Personajes | Tráilers | Episodios | Capturas de pantalla | Popularidad | Descripción |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu es una fuente JSON:API pública nativa de identidad. Las solicitudes GET públicas de solo lectura no requieren credenciales OAuth; Las identificaciones Kitsu confirmadas ya participan en `mappings.db`, y Kitsu también pueden devolver asignaciones MAL/AniList/AniDB directas con resultados de búsqueda y metadatos. Kitsu actualmente aporta búsquedas, metadatos, popularidad, descripciones, episodios y un avance de YouTube cuando esté disponible. Las personas/personajes no se publicitan intencionalmente porque esas relaciones suelen ser escasas.

AniDB es opcional y se habilita solo cuando `ANIDB_CLIENT` está configurado. Jikan **no** es una base de datos de identidad separada: es un backend MAL local que se utiliza para datos que no están disponibles a través del MAL oficial API. Sus licenciantes de tarjetas principales y sus estadísticas de popularidad lazy utilizan puntos finales locales separados, por lo que el raspado de distribución de puntajes no está en la ruta inicial de las tarjetas. AniSearch es una fuente de base de datos nativa de identidad API resuelta a través de bordes de mapeo `anisearch` confirmados. Su público API no expone la búsqueda normal de consulta de títulos, por lo que no se une a la ruta de búsqueda rápida `/anime <title>`. Debido a que AniSearch coloca ID y `/full` en el mismo grupo de limitación estricta, la fuente realiza una búsqueda en caché `/full` por título y mantiene los campos pesados ​​fuera de la agregación inicial; las personas, los personajes y los episodios reutilizan posteriormente esa misma carga útil sin tener que esperar otra red. Las localizaciones en inglés, japonés, alemán, español, francés e italiano AniSearch se utilizan para títulos/sinónimos, sinopsis, títulos de episodios, licenciantes regionales y créditos de voz localizados. Las solicitudes públicas sin token se ajustan al intervalo documentado de familia de ID de 10 segundos (5 segundos con un token válido) y el texto de sinopsis de AniSearch mantiene el enlace de atribución directo requerido AniSearch. El soporte de SkipDB permanece en el código base como un proveedor inactivo respaldado por IMDb, pero no se registra intencionalmente en el tiempo de ejecución porque la cobertura actual de segmentos de salto de anime es demasiado pequeña para justificar su exposición en la interfaz de usuario. Su analizador/configuración/pruebas se conservan para que pueda volver a habilitarse más adelante si mejora la cobertura. SkipDB los datos se sirven bajo ODbL 1.0 + reciprocidad.

## como funciona

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

### Reglas de identidad

`AnimeIdentity` no tiene identificación principal. Nunca se supone que una identificación numérica de una base de datos identifique el mismo título en otra base de datos simplemente porque el número coincide.

La fusión entre fuentes sigue reglas conservadoras:

1. las identificaciones externas compartidas explícitas son pruebas de identidad sólidas;
2. los ID conflictivos del mismo proveedor impiden una fusión;
3. la búsqueda de texto puede utilizar un recurso romaji normalizado exacto restringido solo cuando no existe ningún conflicto con el mismo proveedor;
4. la búsqueda directa de ID **no** utiliza la combinación de títulos únicamente;
5. Las asignaciones de tiempo de ejecución son solo directas y no atraviesan recursivamente cadenas arbitrarias de estilo TVDB/TMDB.

La identidad completamente enriquecida permanece disponible internamente para funciones de enrutamiento y diferidas. El bloque de identificación visible de la tarjeta muestra solo las identificaciones que pertenecen a fuentes de metadatos que realmente contribuyeron a esa tarjeta.

## Buscar

El único comando de búsqueda de cara al usuario es `/anime`.

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
/anime kitsu:<id>
```

`/anime <title>` consulta todos los proveedores de búsqueda registrados en paralelo y recopila un conjunto de resultados de alcance de consulta limitado antes de la paginación Telegram. La relevancia considera títulos, alias, variantes nativas/romaji, coincidencias de tokens/prefijos, transliteración y una alternativa de similitud conservadora.

Los límites estrictos de páginas/elementos protegen las cuotas ascendentes. Cuando el bot no puede demostrar que el recuento recopilado es definitivo, la interfaz de usuario informa un recuento incompleto en lugar de presentarlo como exacto.

Ejecutar `/anime` sin argumentos abre un selector de fuente interactivo. La entrada pendiente se limita al par usuario/chat, caduca automáticamente y se puede cancelar con `/cancel`.

`/anime` también admite la búsqueda inversa de imágenes. Adjunte una imagen al comando o pase una URL de imagen pública y el bot ofrecerá solo motores de búsqueda de imágenes cuya cuota esté disponible actualmente: trace.moe, What Anime Is This o ambos. Los resultados se resuelven a través de AniList ID confirmados y se muestran como la vista previa paginada normal del candidato; la tarjeta de metadatos completa se abre solo después de que el usuario elige **Detalles**. La evidencia coincidente (proveedor, similitud, episodio, marca de tiempo) se mantiene en la vista previa. La acción **¿No es el título que necesitas?** permite intentar otra fuente o cancelarla sin pasar por alto las cuotas del proveedor. Las imágenes rasterizadas cargadas se normalizan a JPEG antes de la búsqueda saliente.

Las credenciales de búsqueda de imágenes son opcionales. trace.moe se ejecuta de forma anónima cuando `TRACE_MOE_API_KEY` está vacío y lee la cuota actual real de `/me`; Las claves configuradas se envían como `x-trace-key`, por lo que las cuotas de socios/donantes se descubren en lugar de codificarse. What Anime Is This se ejecuta como invitado cuando `WHATANIMEISTHIS_API_KEY` está vacío y usa `Authorization: Bearer ...` cuando hay una clave presente. Debido a que su API público no expone el estado de crédito de API clave, el bot mantiene un contador diario local persistente conservador: los valores predeterminados son 5 búsquedas de invitados y 10 búsquedas de API clave, y ambos límites son configurables para cuentas con diferentes políticas de crédito. Configure `WHATANIMEISTHIS_API_DAILY_LIMIT=0` para desactivar el límite de teclas API local y confíe en los errores de crédito/cuota del propio servicio. Una respuesta de cuota del lado del servidor marca inmediatamente que el backend no está disponible para el período de cuota local actual.

## Secciones lazy de la tarjeta

La tarjeta principal mantiene los metadatos primero. Las siguientes secciones se cargan solo cuando se solicita:

- personal y creadores;
- actores de doblaje, incluidos créditos de doblaje AniSearch con etiquetas de idioma;
- personajes y retratos;
- capturas de pantalla;
- distribuciones detalladas de popularidad/clasificación;
- descripciones y texto de referencia fuente;
- trailers/promociones;
- episodios.

Los créditos de voz en japonés siguen siendo la base del idioma original sin etiquetar. Los créditos de doblaje AniSearch se conservan con los sufijos de rol explícitos `[EN]`, `[DE]`, `[ES]`, `[FR]` o `[IT]` para que nunca se hagan pasar por créditos japoneses originales. El personal de localización/ADR está excluido de la lista de personal de producción primaria.

## Requisitos y soporte de plataforma.

El tiempo de ejecución Python está diseñado para **Linux, macOS y Windows** nativo con Python **3.11, 3.12, 3.13 o 3.14**. GitHub Actions ejecuta el conjunto de unidades completo en las tres familias de sistemas operativos para cada versión Python compatible.

- **Linux** — plataforma de producción primaria; El iniciador multiplataforma funciona en distribuciones principales siempre que esté disponible una compilación CPython compatible. El `start.sh` incluido sigue siendo un ayudante de producción `tmux` orientado al Linux.
- **macOS** — compatible con el iniciador Python; `start.command` se proporciona como un envoltorio práctico. `systemd` las unidades de mantenimiento no aplican en macOS.
- **Windows (nativo)**: compatible con el iniciador Python, `start.ps1` o `start.cmd`; No se requiere WSL.
- **Docker + Docker Compose**: opcional en todas las plataformas y utilizado solo para el suplemento Jikan local. El bot todavía funciona sin Docker; El MAL oficial permanece disponible mientras las funciones complementarias exclusivas de Jikan estén deshabilitadas.
- **systemd**: integración opcional de implementación/mantenimiento solo Linux en `deploy/systemd/`.

Ejecute `python scripts/project.py doctor` (o el mismo comando con su intérprete Python activo) para verificar la compatibilidad básica de tiempo de ejecución/dependencia de una máquina.

## Inicio rápido

Primero clona el repositorio:

```text
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

El lanzador canónico es `scripts/project.py`. Crea `.venv`, instala dependencias bloqueadas, crea directorios de configuración faltantes a partir de los ejemplos comprometidos sin sobrescribir los valores existentes y comprende el diseño del entorno virtual nativo en Unix y Windows.

Linux / macOS:

```bash
python3 scripts/project.py setup
# Edit .env.d/telegram.env and add at least BOT_TOKEN.
python3 scripts/project.py check
python3 scripts/project.py run       # foreground
python3 scripts/project.py start     # background + PID file
```

Windows PowerShell/Símbolo del sistema:

```powershell
py -3 scripts\project.py setup
# Edit .env.d\telegram.env and add at least BOT_TOKEN.
py -3 scripts\project.py check
py -3 scripts\project.py run
.\start.ps1                         # background
```

`start.cmd` está disponible para el símbolo del sistema y macOS puede usar `./start.command`. Los procesos en segundo plano iniciados por el iniciador multiplataforma se gestionan con:

```text
python scripts/project.py status
python scripts/project.py stop
python scripts/project.py restart
```

Linux las implementaciones de producción pueden seguir usando `./start.sh`; conserva el flujo de trabajo `tmux` independiente existente. Los registros de tiempo de ejecución permanecen en `logs/YYYY.MM.DD/`, mientras que el iniciador genérico en segundo plano también escribe su stdout/stderr heredado en `logs/launcher.log`.

Los registros de tiempo de ejecución se dividen por responsabilidad en `logs/YYYY.MM.DD/`: `bot.log` contiene eventos de aplicación/tiempo de ejecución, `users.log` contiene Telegram seguimiento de acciones del usuario, `api.log` contiene fuentes salientes/API/reintentos/eventos de estado y `errors.log` duplica todos los `ERROR+` registros para diagnósticos rápidos. El directorio cambia automáticamente después de la medianoche local sin reiniciar el bot.

## Configuración

Todo el análisis del entorno de ejecución está centralizado en `core/settings.py`. Las nuevas implementaciones copian `.env.example.d/` a `.env.d/`. Solo se cargan los archivos fijos `telegram.env`, `sources.env`, `timestamps.env`, `rate-limits.env`, `mappings.env`, `storage.env`, `logging.env` y `runtime.env`; Los archivos perdidos como `backup.env` se ignoran. Las claves duplicadas en los archivos de configuración del proyecto fallan en el inicio, mientras que las variables de entorno del proceso real tienen la máxima prioridad. Un `.env` monolítico sigue siendo compatible sólo como ruta de migración.

### Configuraciones esenciales

| Variables | Requerido | Propósito |
| --- | :---: | --- |
| `BOT_TOKEN` | Sí | Telegram token de bot de BotFather. |
| `MAL_CLIENT_ID` | Recomendado | Habilita la búsqueda y los metadatos oficiales MyAnimeList. |
| `ANIDB_CLIENT` | No | Habilita AniDB HTTP API metadatos/personas/episodios. |
| `ANIDB_CLIENT_VERSION` | No | Registrado AniDB HTTP API versión del cliente; El valor predeterminado es `1`. |
| `ANILIST_ACCESS_TOKEN` | No | Token AniList opcional cuando se desea acceso autenticado. |
| `KITSU_API_URL` | No | Kitsu pública JSON:API URL base; El valor predeterminado es `https://kitsu.io/api/edge`. |
| `TRACE_MOE_API_KEY` | No | Opcional tecla trace.moe API (`x-trace-key`); el modo gratuito funciona sin él y la cuota se lee desde `/me`. |
| `WHATANIMEISTHIS_API_KEY` | No | Opcional What Anime Is This API clave enviada como `Authorization: Bearer ...`; El modo de invitado gratuito funciona sin él. |
| `IMAGE_SEARCH_DB_PATH` | No | SQLite ruta para una contabilidad de cuotas de búsqueda de imágenes persistente y conservadora. |
| `ADMIN_TELEGRAM_USER_IDS` | No | ID de usuario administrador Telegram separados por coma/espacio/punto y coma. |
| `TELEGRAM_BOT_API_URL` | No | Punto final Telegram Bot API personalizado/autohospedado. |
| `TELEGRAM_BOT_API_LOCAL_FILE_ROOT` | No | Directorio de host asignado a `/var/lib/telegram-bot-api` cuando las rutas de archivo del Bot local API están dentro de un contenedor. |
| `USER_SETTINGS_DB_PATH` | No | SQLite ruta para la configuración por usuario y el registro de usuarios conocidos. |
| `BANS_DB_PATH` | No | SQLite ruta para prohibiciones de moderación. |
| `MAPPINGS_DB_PATH` | No | Base de datos de mapeo de ID cruzado en tiempo de ejecución. |

No confirme `.env`, `.env.d/`, `.proxies.d/`, tokens de bot, tokens de acceso, contraseñas, credenciales de proxy o credenciales privadas API.

### Grupos de proxy por fuente

El enrutamiento de proxy saliente opcional se configura por separado en `.proxies.d/`, un archivo TOML fijo por fuente de tiempo de ejecución más `telegram.toml` para el propio bot. Empiece desde `.proxies.example.d/`. Los esquemas de proxy admitidos son `http`, `socks4` y `socks5`.

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

Los perfiles son independientes: `mal.toml` afecta solo a MAL, `anilist.toml` solo a AniList, y así sucesivamente. Los valores `priority` más altos se prueban antes que los valores más bajos independientemente del orden TOML. Las inscripciones empatadas con la misma prioridad se seleccionan por turnos; los niveles de menor prioridad se utilizan solo como conmutación por error después de que falla el nivel superior. Se permiten URL de proxy duplicadas cuando tienen nombres de entrada distintos, por lo que repetir un punto final puede darle intencionalmente más peso de rotación. `enabled = false` puede desactivar todo el perfil o una entrada individual. Si al menos una entrada de proxy está activa para un perfil, ese perfil **no** vuelve silenciosamente a la conexión directa cuando todos los servidores proxy fallan; El acceso directo se utiliza sólo cuando el perfil no tiene proxies activos. La configuración del proxy se carga al inicio del proceso, por lo que las ediciones surten efecto después de reiniciar el bot. Cuando `telegram.toml` tiene servidores proxy activos, este bot omite intencionalmente cualquier punto final `telegram-bot-api` local/compartido configurado y habla con el `api.telegram.org` oficial a través de su propio grupo de proxy; esto mantiene el alcance del proxy para este bot en lugar de cambiar otros bots que comparten el servidor local. `jikan.toml` también es especial: el servicio Python de salto al bucle invertido Jikan permanece directo, mientras que el proxy seleccionado se reenvía al servicio Jikan local y se aplica a su raspado MyAnimeList saliente.

Los perfiles de tiempo de ejecución fijos son: `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `bahamut`, `baha_anime_skip`, `skipdb`, `trace_moe` y `whatanimeisthis`. Los archivos TOML perdidos se ignoran. Los archivos proxy pueden contener credenciales y se ignoran; `start.sh` mantiene `.proxies.d` en el modo `700` y los archivos de perfil conocidos en el modo `600`.

### Perfiles de usuario-agente por fuente

Las anulaciones opcionales de User-Agent se encuentran en `.user-agents.d/` con los mismos nombres de perfil fijos que el enrutamiento proxy. Si un perfil no tiene una entrada personalizada activa, las solicitudes utilizan el Agente de usuario del proyecto integrado (`anime-db-bot/<version> (...)`). Mayor `priority` gana; las entradas vinculadas con la prioridad activa más alta rotan entre solicitudes. Los agentes de usuario de menor prioridad permanecen en espera hasta que se deshabiliten las entradas de mayor prioridad.

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

El límite de la red anula los encabezados `User-Agent` locales del proveedor, por lo que el valor del perfil seleccionado tiene autoridad. Para `jikan`, el User-Agent seleccionado se reenvía a través del servicio loopback y se aplica a su solicitud saliente MyAnimeList. Para `telegram`, un agente de usuario personalizado activo cambia este bot de un punto final `telegram-bot-api` compartido/local al `api.telegram.org` oficial, asegurando que el encabezado configurado llegue a la solicitud externa Telegram. `.user-agents.d` se ignora y se carga al inicio del proceso.

### AniDB

La integración utiliza el AniDB HTTP API. Requiere un HTTP API **nombre y versión del cliente** registrado, no una contraseña de cuenta AniDB.

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

AniDB Las respuestas XML se almacenan en caché en el disco y las solicitudes de red se serializan con un intervalo de solicitud mínimo adicional para respetar las expectativas API del servicio.

### MAL / Jikan

MAL es la fuente de identidad. Jikan es un backend complementario local y nunca introduce una clave de identidad `jikan`.

El servicio incluido se encuentra en:

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Una interrupción Jikan no hace que la búsqueda/metadatos oficiales de MAL no estén disponibles.

## Comandos

### Comandos de usuario

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

### Comandos de administrador

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

El mapeo de mutaciones es intencionalmente de dos pasos. `/mapping_set` y `/mapping_delete` crean una mutación pendiente de corta duración; la base de datos cambia solo después de `/mapping_confirm <token>`. El historial de auditoría registra el Telegram administrador responsable del cambio.

## Localización

El modelo de dominio es localmente neutral. Los adaptadores de origen normalizan los valores de estado/tipo/temporada/género/rol ascendentes en claves canónicas, y la traducción ocurre solo en el momento del renderizado.

Configuraciones regionales de UI soportadas:

- `en` — Inglés (**predeterminado y alternativo**);
- `ru` — Русский;
- `ja` — 日本語;
- `de` — Alemán;
- `es` — Español;
- `fr` — Francés;
- `it` — Italiano.

Los usuarios existentes mantienen su configuración regional guardada explícitamente. Los usuarios nuevos, las configuraciones faltantes, los valores locales no válidos y las claves de traducción faltantes vuelven al inglés.

El texto fuente de formato libre, como las descripciones de anime, no se traduce automáticamente. Consulte [`localization/README.md`](../localization/README.md) para conocer la arquitectura de localización y las reglas de mantenimiento.

## Persistencia

El tiempo de ejecución mantiene separados los diferentes tipos de estados:

- configuración de usuario y usuarios conocidos: SQLite, con alcance de `(platform, user_id)`;
- prohibiciones: tienda SQLite persistente separada;
- `mappings.db` — base de datos de resolución de ID cruzada respaldada en disco;
- AniDB XML: caché de disco;
- Telegram sesiones de devolución de llamada de tarjeta/búsqueda: estado TTL/LRU en memoria limitado.

Las configuraciones de usuario heredadas creadas antes del alcance de la plataforma se migran como registros Telegram sin cambiar la configuración regional guardada.

## Resiliencia y limitación de velocidad

La salida HTTP utiliza instancias `httpx.AsyncClient` compartidas propiedad de `AppContext`. Las fallas de origen se normalizan en errores escritos y pasan a través de una capa de reintento/disyuntor común.

El registro sanitario de origen admite:

- manejo de fallas transitorias versus no transitorias;
- reintentos limitados con retroceso;
- umbrales de disyuntores;
- tiempos de reutilización;
- exactamente una sonda de recuperación medio abierta.

Los límites personales Telegram están limitados por `(platform, user_id)`. Los administradores pueden omitir el limitador personal, pero **nunca** omitir los límites de seguridad del proveedor anterior.

## Arquitectura

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

`services/runtime/app_context.py` es la raíz de la composición de la aplicación. Las dependencias del tiempo de ejecución de producción deben pertenecer allí en lugar de crearse como elementos únicos del servicio de tiempo de importación.

Más detalle: [`docs/app-context.md`](app-context.md).

## Mapeos de ID cruzada

El actualizador de mapas transmite varios conjuntos de datos externos a SQLite, registra la procedencia/evidencia/conflictos, valida la base de datos reconstruida y la intercambia atómicamente en su lugar. El gráfico completo no se carga en la RAM.

Las anulaciones direccionales manuales admiten `accept` y `reject`, transportan metadatos de autor/motivo/marca de tiempo y preservan el historial de solo agregar en las reconstrucciones.

Los comandos de mantenimiento están disponibles a través del iniciador multiplataforma:

```text
python scripts/project.py mappings --status
python scripts/project.py mappings --override-list
python scripts/project.py mappings --override-history
```

El contenedor Unix `./scripts/update-mappings.sh` permanece disponible para implementaciones existentes.

## Desarrollo

Utilice el mismo iniciador en todos los sistemas operativos compatibles:

```text
python scripts/project.py setup --dev
python scripts/project.py check
python scripts/project.py doctor
```

En Windows, se puede usar `py -3 scripts\project.py ...` en lugar de `python`. Los archivos Unix `./scripts/setup.sh` y `./scripts/check.sh` son envoltorios convenientes para la misma implementación. Los comandos directos del entorno virtual siguen estando disponibles en `.venv/bin/python` en Unix y `.venv\Scripts\python.exe` en Windows.

GitHub Actions requiere que el conjunto de unidades completo pase **Ubuntu, macOS y Windows** para Python 3.11, 3.12, 3.13 y 3.14. Cada trabajo de matriz también ejecuta el lanzador médico multiplataforma. El trabajo de calidad Linux ejecuta además Ruff comprobaciones de corrección, comprobaciones del formateador para la base escrita, mypy para la base escrita, pruebas completas con una puerta de cobertura de al menos el 70% y ShellCheck para contenedores de shell Unix.

## Colaboradores

- [OpenAI Codex](https://github.com/apps/openai-codex) — aplicación oficial de Codex en GitHub; desarrollo e implementación del proyecto asistidos por IA.

## Contribuyendo

Las contribuciones son bienvenidas. Lea [CONTRIBUTING.md](../CONTRIBUTING.md) antes de abrir una solicitud de extracción y siga el proyecto [Código de conducta](../CODE_OF_CONDUCT.md)]. Los informes de errores y las solicitudes de funciones deben utilizar los formularios de problemas del repositorio.

## Seguridad

- Mantenga `.env` y las credenciales fuera del control de versiones.
- Los registros utilizan archivos `bot/users/api/errors` diarios, redacción secreta de forma predeterminada, ID de correlación por actualización, marcas de tiempo de zona horaria local en tiempo de ejecución y rotación limitada por archivo. `LOG_REDACT_SECRETS=0` desactiva deliberadamente todos los enmascaramientos para diagnósticos locales y puede escribir las credenciales palabra por palabra; manténgalo habilitado en registros compartidos/públicos.
- Las acciones exclusivas del administrador deben permanecer detrás de la capa de control de acceso.
- No exponga públicamente un Telegram Bot API autohospedado, un punto final de métricas futuras o un API externo futuro sin controles explícitos de autenticación/red.
- Las anulaciones de asignación se auditan porque un borde de identidad incorrecto puede afectar múltiples capacidades.

Para obtener informes de vulnerabilidades y canales de seguridad admitidos, consulte [SECURITY.md](../SECURITY.md). No publique credenciales, tokens ni detalles de implementación privada en una edición pública.

## Estado del proyecto

El proyecto está en desarrollo activo. Se implementan el flujo central de búsqueda/tarjeta Telegram, el modelo de identidad, la base de datos de mapeo, la agregación de fuentes múltiples, la localización, las capacidades diferidas, la persistencia, la resiliencia y la base de CI. Se planea trabajar con filtros de descubrimiento/búsqueda adicionales, integraciones de cuentas de usuario, notificaciones, monitoreo/métricas de Prometheus, soporte externo API/Mini App y más fuentes.

## Licencia

Licenciado bajo la [Licencia Apache 2.0](../LICENSE). Puede utilizar, modificar y distribuir el proyecto según sus términos; preservar los avisos requeridos y marcar las modificaciones significativas según lo requiera la licencia.

## Fuentes de datos y agradecimientos

`anime-db-bot` se integra o se basa en datos de proyectos y servicios que incluyen:

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Kitsu](https://kitsu.app/) - público de solo lectura JSON:API; no se requiere OAuth para solicitudes GET normales
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) — Base de datos API metadatos; Se aplican requisitos de atribución y enlace de sinopsis.
- [SkipDB](https://skipdb.tv/) - datos de salto de segmento en ODbL 1.0 + reciprocidad

Los datos de mapeo entre identificaciones se recopilan a partir de múltiples conjuntos de datos comunitarios. Cada servicio ascendente y conjunto de datos sigue sujeto a sus propios términos, límites de tarifas y requisitos de atribución.

Kitsu las solicitudes GET públicas de solo lectura se utilizan sin credenciales OAuth. El tiempo de ejecución aplica sus propios límites de solicitudes conservadores porque no se asume ningún contrato de límite de velocidad del lado del servidor estable.

AniSearch Base de datos API las solicitudes de metadatos de solo lectura no requieren OAuth. `ANISEARCH_APP_ID` y `ANISEARCH_APP_SECRET` son credenciales de aplicación OAuth opcionales reservadas para futuras funciones AniSearch autorizadas por el usuario; nunca se envían con solicitudes de bases de datos de solo lectura.
