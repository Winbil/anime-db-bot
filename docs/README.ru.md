> **Проект разработан при помощи AI.**

<p align="center">
  <a href="../README.md">English</a> · <strong>Русский</strong> · <a href="README.ja.md">日本語</a> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

Telegram-бот для поиска аниме и объединения сведений из независимых баз данных. В одном интерфейсе доступны карточки тайтлов, серии, персонажи, авторы и связанные произведения.

## Возможности

- Поиск по названию, внешнему ID или изображению с постраничным просмотром результатов.
- Объединённые рейтинги, описания, даты выхода, персонажи, команда, связи и рекомендации.
- Серии, сведения об OP/ED и доступные таймкоды пропуска; тяжёлые разделы загружаются при открытии.
- Осторожное сопоставление тайтлов: объединяются только подтверждённые идентификаторы.
- Сохраняемые настройки, администрирование, ограничения запросов и отдельные профили прокси/User-Agent.
- Интерфейс на семи языках с сохранением оригинальных данных источников.

## Источники данных

Для метаданных используются MyAnimeList (с Jikan в качестве дополнительного источника), AniList, Shikimori, Kitsu, AniDB (при наличии регистрации клиента) и AniSearch. Остальные сервисы предоставляют отдельные функции, а не заменяют основные базы аниме.

| Возможности | Источники данных |
| --- | --- |
| Поиск и метаданные | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Дополнительный рейтинг | [IMDb](https://www.imdb.com/) |
| Поиск по изображению | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Серии, темы и таймкоды | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) предоставляет соответствия ID между базами. Провайдер SkipDB для таймкодов пока не активирован; наличие источника в списке не гарантирует данных для каждого тайтла или серии.

## Быстрый старт

Требуются Python 3.11–3.14 и Linux, macOS или Windows. Клонируйте проект и запустите универсальный установщик:

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# Укажите BOT_TOKEN в .env.d/telegram.env
python3 scripts/project.py check
python3 scripts/project.py run
```

В Windows используйте `py -3 scripts\project.py` вместо `python3 scripts/project.py`. Для фонового запуска доступна команда `python3 scripts/project.py start` (также `status`, `restart`, `stop`); на Linux можно использовать `./start.sh`.

## Использование

Команда `/anime` открывает выбор источника или поиск по названию. Изображение, прикреплённое к `/anime`, либо публичная ссылка включает обратный поиск, если доступен провайдер. `/settings` меняет настройки, `/cancel` отменяет ввод.

```text
/anime Frieren
/anime mal:5114
/anime anilist:<id>
/anime shikimori:<id>
/settings
/ping
/cancel
```

## Настройка

Обязателен только `BOT_TOKEN`. Данные доступа к источникам задаются по необходимости: `MAL_CLIENT_ID` расширяет возможности MyAnimeList, `ANIDB_CLIENT` включает AniDB. Для гостевого поиска по картинке API-ключи необязательны. Прокси и User-Agent настраиваются в `.proxies.d/` и `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Бот загружает и проверяет релизы **Anime Mapping DB**, используя `mappings.db` напрямую. Он не собирает базу сопоставлений и не зависит от **Anime Timestamp DB**.

## Документация

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Лицензия и атрибуция

Код распространяется по Apache-2.0. Сторонние сервисы и наборы данных сохраняют собственные лицензии, условия API и требования к указанию авторства. Не храните токены в репозитории. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
