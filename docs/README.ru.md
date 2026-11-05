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

## Поиск и навигация

Команда `/anime` принимает название или явный ID конкретного сервиса. Сначала отображаются результаты с пагинацией, затем открывается подробная карточка. Поиск учитывает варианты названий и письменности, но прямой поиск по ID никогда не объединяет тайтлы исключительно по названию.

Обратный поиск принимает изображение из Telegram или публичную ссылку. Доступные провайдеры показывают степень сходства, серию и время кадра ещё до открытия карточки. Гостевые и авторизованные лимиты учитываются отдельно.

Основная карточка содержит нормализованную информацию о тайтле. Персонажи, команда, сэйю, кадры, подробная статистика оценок, описания, трейлеры, связанные работы, рекомендации и серии загружаются по запросу. Группы сезонов, куров и спецвыпусков отображаются только при наличии таких данных у источника.

## Источники данных

Для метаданных используются MyAnimeList (с Jikan в качестве дополнительного источника), AniList, Shikimori, Kitsu, AniDB (при наличии регистрации клиента) и AniSearch. Остальные сервисы предоставляют отдельные функции, а не заменяют основные базы аниме.

| Возможности | Источники данных |
| --- | --- |
| Поиск и метаданные | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| Дополнительный рейтинг | [IMDb](https://www.imdb.com/) |
| Поиск по изображению | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| Серии, темы и таймкоды | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) предоставляет соответствия ID между базами. Провайдер SkipDB для таймкодов пока не активирован; наличие источника в списке не гарантирует данных для каждого тайтла или серии.

## Возможности источников

| Источник | Поиск | Метаданные | Команда | Персонажи | Серии | Связи | Рекомендации |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch дополняет подтверждённые тайтлы локализованными данными и дубляжными голосами, но не участвует в обычном поиске по названию. AnimeThemes даёт сведения об OP/ED на уровне серии. Поддержка SkipDB в runtime пока отключена.

## Идентичность и объединение данных

В проекте нет «главной» внешней базы аниме. Идентификаторы MAL, AniList, Shikimori, Kitsu, AniDB и AniSearch остаются независимыми до подтверждённого сопоставления. Совпадение числа, похожее название или принадлежность к одной франшизе не считаются доказательством.

Сопоставление выполняется только по прямым подтверждённым связям с учётом конфликтов. При агрегации сохраняется происхождение данных; при наличии поддержки можно просматривать отдельные источники. Для рейтинга IMDb нужна однозначная связь с аниме-базой: одних промежуточных ID TVDB/TMDB недостаточно.

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

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

## Развёртывание и запуск

Универсальный launcher создаёт окружение, выполняет проверки и управляет фоновым процессом. Для Linux есть запуск через `start.sh` и tmux. В Windows доступны `start.ps1`/`start.cmd`, а в macOS — `start.command`.

Docker Compose и локальный Jikan необязательны: официальный MAL продолжает работать без них. Для Linux предусмотрены вспомогательные unit-файлы `systemd` в `deploy/systemd/`; на Windows и macOS они не нужны.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

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

## Команды Telegram

Основная пользовательская команда — `/anime`. Администраторские команды требуют разрешённых Telegram ID и защищены проверкой доступа. Изменение сопоставлений проходит через подтверждение, после чего сохраняется история операции.

| Команда | Назначение |
| --- | --- |
| `/start`, `/ping` | Приветствие и проверка доступности |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | Поиск по названию, ID или изображению |
| `/settings` | Язык и пользовательские настройки |
| `/cancel` | Отмена ожидаемого ввода |
| `/users`, `/status`, `/source_health` | Список пользователей, состояние бота и источников |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | Блокировка или разблокировка пользователя |
| `/mapping_overrides`, `/mapping_history [limit]` | Просмотр исключений и истории сопоставлений |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | Подготовка изменения и его подтверждение/отмена |

## Настройка

Обязателен только `BOT_TOKEN`. Данные доступа к источникам задаются по необходимости: `MAL_CLIENT_ID` расширяет возможности MyAnimeList, `ANIDB_CLIENT` включает AniDB. Для гостевого поиска по картинке API-ключи необязательны. Прокси и User-Agent настраиваются в `.proxies.d/` и `.user-agents.d/`.

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

Бот загружает и проверяет релизы **Anime Mapping DB**, используя `mappings.db` напрямую. Он не собирает базу сопоставлений и не зависит от **Anime Timestamp DB**.

## Справочник настроек

Примеры конфигурации копируются в `.env.d/` без перезаписи существующих значений. Загружаются только предусмотренные файлы. Переменные окружения процесса имеют приоритет, а повтор одного ключа в файлах проекта вызывает ошибку запуска. Не добавляйте секреты в Git.

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | Токен Telegram-бота (обязателен) |
| `MAL_CLIENT_ID` | ID клиента официального MyAnimeList API |
| `ANIDB_CLIENT` | Необязательное имя клиента AniDB HTTP API |
| `ANILIST_ACCESS_TOKEN` | Необязательная авторизация AniList |
| `TRACE_MOE_API_KEY` | Ключ trace.moe; есть гостевой режим |
| `WHATANIMEISTHIS_API_KEY` | Ключ What Anime Is This; есть гостевой режим |
| `ADMIN_TELEGRAM_USER_IDS` | Telegram ID администраторов |
| `TELEGRAM_BOT_API_URL` | Адрес собственного Telegram Bot API |
| `MAPPINGS_DB_PATH` | Путь к базе соответствий ID |
| `IMDB_RATINGS_BACKEND` | Режим рейтингов IMDb: local/API/off |
| `BAHA_ANIME_SKIP_DB_PATH` | Путь к локальному индексу Baha |

Для каждого источника можно задать отдельный TOML-профиль в `.proxies.d/`. Поддерживаются HTTP, SOCKS4 и SOCKS5. Приоритет определяет порядок, равноприоритетные прокси чередуются, резервные используются при отказе. Если активный профиль не работает, автоматического перехода на прямое соединение нет.

Профили User-Agent хранятся в `.user-agents.d/` и тоже поддерживают приоритеты. Изменения применяются после перезапуска. Собственный сервер Telegram Bot API необязателен и должен быть защищён.

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

Доступные переменные и названия профилей перечислены в шаблонах `.env.example.d/`, `.proxies.example.d/` и `.user-agents.example.d/`.

## Локальные данные и обслуживание

Обновлятор получает версионированный `mappings.db.zst`, проверяет контрольные суммы и атомарно заменяет локальную базу, сохраняя проверенные администраторские исключения. Бот использует только компактную runtime-базу, без evidence-базы сопоставлений.

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

Локальный индекс IMDb сохраняет лишь рейтинги, привязанные к подтверждённым ID аниме, а не весь исходный дамп. Baha Anime Skip индексируется локально: во время работы бот не запрашивает таймкоды напрямую у Bahamut. Оба индекса обновляются отдельно после появления mappings.db.

Настройки пользователей, реестр пользователей, блокировки и отдельные лимиты хранятся в SQLite. Журналы распределены по `logs/YYYY.MM.DD/`: `bot.log`, `users.log`, `api.log`, `errors.log`. Фоновый launcher также пишет `logs/launcher.log`.

## Серии, OP/ED и таймкоды

Источники списка серий и таймкодов независимы. Выбранный провайдер серий не диктует источник таймкодов: каждый сервис использует собственную систему ID и нумерацию. Если соответствие нельзя доказать, отсутствие данных лучше неверной привязки к похожему эпизоду.

AnimeThemes дополняет серии названиями опенингов/эндингов, песнями, исполнителями и ссылками на видео. Источники таймкодов могут возвращать OP, ED, recap и другие сегменты; интервалы иногда различаются из-за нумерации серий и конкретного видеомонтажа. Один найденный диапазон не означает согласие всех провайдеров.

## Эксплуатация и диагностика

Если тайтл не находится, сначала проверьте, какой источник ответил и есть ли для него подтверждённое сопоставление. Ошибка отдельного API или отсутствие необязательного ключа не должны останавливать весь поиск. `/status` показывает статистику процесса, а `/source_health` — состояние защитных ограничителей.

При ошибке запуска используйте `doctor` и `check`, проверьте `logs/YYYY.MM.DD/errors.log` и наличие `BOT_TOKEN`. Изменения `.env.d/`, прокси и User-Agent требуют перезапуска. Прежде чем пересоздавать индексы IMDb/Baha, проверьте статус mappings и его манифест.

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## Архитектура и отказоустойчивость

Поиск, разрешение ID, API-адаптеры, агрегация, локализация, хранение и Telegram-интерфейс отделены друг от друга. Тайм-ауты, повторы, ограничения запросов и circuit breakers помогают переживать сбои отдельных сервисов.

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

## Разработка и безопасность

Изменения должны сохранять осторожную модель идентичности и не перегружать главную карточку лишними сетевыми запросами. Перед PR запускайте проверки на поддерживаемом Python. Об уязвимостях сообщайте по правилам безопасности, не публикуйте токены в issues.

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md) · [Code of Conduct](../CODE_OF_CONDUCT.md)

## Документация

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## Лицензия и атрибуция

Код распространяется по Apache-2.0. Сторонние сервисы и наборы данных сохраняют собственные лицензии, условия API и требования к указанию авторства. Не храните токены в репозитории. [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
