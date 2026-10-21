# anime-db-bot

Telegram-бот для поиска аниме и сборки одной общей карточки из нескольких баз данных.

Главный принцип проекта: **поиск, metadata sources, агрегирование и Telegram UI — отдельные слои**. Канонический ID между слоями сейчас — MAL ID.

## Что подключено

### Поиск

Обычный `/anime` использует параллельно:

- Shikimori Search;
- MyAnimeList Search.

Результаты объединяются строго по MAL ID. `/search` позволяет явно выбрать MAL, Shikimori, AniList, несколько источников или все сразу.

Если результат пришёл только из MAL/AniList и в нём нет Shikimori ID, `services/id_resolver.py` выполняет отдельное разрешение cross-ID. Результат принимается только если найденная запись Shikimori имеет **тот же MAL ID**, поэтому metadata source не выполняет скрытый поиск сам.

### Метаданные

После выбора аниме используются:

- Shikimori;
- AniList;
- MyAnimeList.

`AnimeAggregator` объединяет семантически одинаковые данные: названия, жанры, студии, даты, статусы, оценки, персонал и другие поля. Источник сохраняется там, где provenance действительно нужен: внешние ID/URL, описания, варианты названий, staff/voices и портреты.

## Ленивая загрузка персонала

Главная карточка **не ждёт тяжёлые списки людей**.

- AniList staff загружается при первом открытии `Авторы и команда`.
- AniList Japanese voice actors загружаются при первом открытии `Сэйю`.
- Shikimori character-backed seiyuu (`anime roles -> character -> seyu`) загружаются при первом открытии `Сэйю`.
- Уже загруженные данные вливаются в текущую `AggregatedAnime` без повторного запроса MAL/AniList/Shikimori основной метадаты.
- Одновременные загрузки источников запускаются параллельно.
- Повторные открытия используют данные текущей карточки и RAM-кеши источников.

Для Shikimori REST есть общий для процесса rate limiter и повторные попытки после HTTP 429. Это не даёт нескольким пользователям одновременно превысить лимит запросов при загрузке большого каста.

## Команды

```text
/start
/ping
/anime <название>
/search <название>
/search mal <название>
/search shikimori <название>
/search anilist <название>
/search all <название>
/search mal,shikimori <название>
```

Примеры:

```text
/anime о моем перерождении в слизь
/search shikimori о моем перерождении в слизь
/search mal slime
/search mal,anilist slime
```

## Архитектура

```text
anime-db-bot/
├── .github/
│   └── workflows/
│       └── ci.yml
├── bots/
│   ├── common.py
│   ├── official.py
│   ├── people_portraits.py
│   ├── runner.py
│   ├── search_ui.py
│   └── tgapi.py
├── core/
│   ├── canonicalization.py
│   ├── contracts.py
│   ├── http_config.py
│   └── models.py
├── search/
│   ├── registry.py
│   └── providers/
│       ├── anilist.py
│       ├── mal.py
│       └── shikimori.py
├── services/
│   ├── aggregator.py
│   ├── id_resolver.py
│   └── search.py
├── sources/
│   ├── anilist.py
│   ├── mal.py
│   ├── registry.py
│   ├── shikimori.py
│   └── shikimori_people.py
├── tests/
│   ├── test_aggregator.py
│   ├── test_anilist_lazy.py
│   ├── test_search.py
│   └── test_shikimori_people.py
├── .env.example
├── .gitignore
├── requirements.txt
├── start.sh
└── README.md
```

## Поток данных

```text
/anime или /search
        │
        ▼
 Search providers
        │
        ▼
SearchCandidate (MAL ID + известные cross-ID)
        │
        ├── при необходимости: MAL -> Shikimori ID resolver
        │
        ▼
 metadata sources
 Shikimori + AniList + MAL
        │
        ▼
 AnimeAggregator
        │
        ▼
 AggregatedAnime
        │
        ▼
 Telegram rich card
        │
        ├── Авторы и команда -> lazy people loaders
        └── Сэйю             -> lazy people loaders
```

## SearchService

`services/search.py`:

1. нормализует запрос;
2. параллельно вызывает выбранные поисковики;
3. изолирует ошибку одного провайдера;
4. объединяет записи по MAL ID;
5. объединяет aliases, cross-ID и оценки;
6. для кириллического запроса предпочитает русское название Shikimori;
7. ограничивает объединённую страницу реальным `page_size`;
8. использует RAM LRU-кеш успешных страниц.

Частично сломанная страница с ошибкой одного провайдера **не кешируется**, поэтому временный сбой не остаётся в памяти на весь TTL.

Настройки:

```env
SEARCH_CACHE_TTL_SECONDS=21600
SEARCH_CACHE_MAX_ENTRIES=500
```

## Metadata contracts

Search provider:

```python
async def search(query: str, *, page: int, limit: int) -> SearchPage:
    ...
```

Metadata source:

```python
async def get_details(
    mal_id: str,
    known_ids: dict[str, str],
) -> AnimeRecord | None:
    ...
```

Тяжёлые источники людей дополнительно могут предоставлять:

```python
async def load_staff(mal_id: str, known_ids: dict[str, str]) -> list[PersonCredit]: ...
async def load_voices(mal_id: str, known_ids: dict[str, str]) -> list[PersonCredit]: ...
```

Metadata source сам не должен выполнять текстовый поиск.

## Персонал и портреты

`PersonCredit` хранит:

- предпочтительное имя;
- aliases на других языках;
- роли;
- source-local external IDs;
- source-keyed portraits.

Пример provenance:

```python
{
    "AniList": ["..."],
    "Shikimori": ["..."],
}
```

При слиянии внешний ID используется как сильный сигнал идентичности. Если два человека имеют одинаковое имя, но конфликтующие ID одной базы, они не объединяются только по имени.

Локализационные/dub credits удаляются из оригинального staff целиком. Для сэйю сохраняется только оригинальная японская озвучка из соответствующих связей источника.

В Telegram страница `0` показывает людей без портрета, затем идёт один человек на страницу; при наличии нескольких портретов используется rich slideshow. Кнопки конкретного источника появляются только если у этого источника действительно есть портреты.

## Описания и названия

Названия, staff и voices сохраняют source buckets для переключения источника. Описания также сохраняются по источнику и выбираются пользователем в UI — бот не заменяет их одним «самым длинным» текстом.

## Кеши персонала

Shikimori:

```env
SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS=21600
SHIKIMORI_REST_MIN_INTERVAL_SECONDS=0.24
```

AniList:

```env
ANILIST_PEOPLE_MAX_PAGES=4
ANILIST_PEOPLE_CACHE_TTL_SECONDS=21600
```

Кеши находятся в RAM и очищаются при перезапуске процесса.

## Зависимости

Прямые runtime-зависимости закреплены точными версиями в `requirements.txt`, чтобы обычный `./start.sh` не подтягивал неожиданно новую minor/patch-версию основного пакета.

## Тесты и CI

GitHub Actions запускает на Python 3.11, 3.12 и 3.13:

```bash
python -m compileall -q bots core search services sources tests
python -m unittest discover -s tests -v
```

Regression-тесты покрывают:

- ограничение объединённой поисковой страницы;
- кеширование успешных и повторный запрос ошибочных search pages;
- идентичность персонала по source IDs;
- фильтрацию localization staff;
- source-keyed portrait merge;
- Shikimori `character -> seyu` parsing;
- отсутствие AniList people pagination в initial metadata path.

`start.sh` дополнительно выполняет быстрые smoke checks перед запуском процесса.

## Запуск

```bash
cp .env.example .env
nano .env
./start.sh
```

Минимально нужен:

```env
BOT_TOKEN=...
```

Для MAL Search/metadata нужен:

```env
MAL_CLIENT_ID=...
```

`start.sh`:

1. проверяет файлы и системные команды;
2. создаёт/проверяет `.venv`;
3. устанавливает закреплённые зависимости;
4. выполняет `pip check` и smoke checks;
5. запускает бота в `tmux`;
6. пишет runtime-лог в `logs/bot.log` (`logs/` исключён из Git).

Если `TELEGRAM_BOT_API_URL` пуст, используется официальный Bot API. Если указан — запускается transport для custom/self-hosted Telegram Bot API.
