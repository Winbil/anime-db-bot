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

## Fuentes de datos

Los metadatos provienen de MyAnimeList (con Jikan como complemento), AniList, Shikimori, Kitsu, AniDB (registro de cliente opcional) y AniSearch. Otros servicios aportan funciones concretas.

| Funciones | Fuentes de datos |
| --- | --- |
| Búsqueda y metadatos | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Valoraciones adicionales | [IMDb](https://www.imdb.com/) |
| Búsqueda por imagen | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Episodios, temas e intervalos | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) proporciona las correspondencias entre IDs de servicios. El proveedor de intervalos SkipDB está desactivado; enumerar una fuente no garantiza datos para todos los títulos o episodios.

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

## Configuración

Se requiere `BOT_TOKEN`. Las demás credenciales son opcionales: `MAL_CLIENT_ID` amplía MyAnimeList y `ANIDB_CLIENT` activa AniDB. La búsqueda de imágenes admite modo invitado. Los perfiles de proxy y User-Agent están en `.proxies.d/` y `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

El bot descarga y verifica las versiones de **Anime Mapping DB**, consultando `mappings.db` directamente. No genera correspondencias ni depende de **Anime Timestamp DB**.

## Documentación

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Licencia y atribuciones

El código usa Apache-2.0. Los servicios y datasets externos conservan sus licencias, condiciones de atribución y de API. No incluya credenciales en los commits. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
