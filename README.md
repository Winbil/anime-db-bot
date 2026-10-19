# anime-db-bot

Telegram-бот для поиска аниме и объединения информации из нескольких внешних баз данных в одну карточку.

Сейчас подключён один источник — **Shikimori**, но архитектура уже построена так, чтобы поиск, агрегация и Telegram-интерфейс не зависели от конкретной базы данных.

## Что умеет бот

- `/start` — показывает краткую информацию о режиме Telegram API и подключённых источниках;
- `/ping` — проверяет, что бот работает;
- `/anime <название>` — ищет аниме сразу во всех подключённых источниках;
- объединяет одинаковые результаты разных источников в один вариант;
- после выбора запрашивает подробности у всех источников;
- объединяет названия, оценки, жанры, студии, описания, персонал, сэйю, постеры, ссылки и внешние ID;
- показывает результат как интерактивную rich-карточку Telegram;
- позволяет открывать `Описание`, `Все названия`, `Авторы и команда` и `Сэйю` нажатием на текст внутри сообщения;
- оставляет обычные inline-кнопки только для `← Назад` и перелистывания `◀️ / ▶️`;
- поддерживает официальный `api.telegram.org` и свой `telegram-bot-api`.

---

# Архитектура

```text
anime-db-bot/
├── core/
│   ├── __init__.py
│   ├── contracts.py
│   └── models.py
│
├── services/
│   ├── __init__.py
│   ├── search.py
│   └── aggregator.py
│
├── sources/
│   ├── __init__.py
│   ├── registry.py
│   └── shikimori.py
│
├── bots/
│   ├── __init__.py
│   ├── common.py
│   ├── official.py
│   └── tgapi.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── start.sh
└── README.md
```

Архитектура специально разделена на четыре слоя.

## `core/`

Это общий формат данных, который не зависит ни от Telegram, ни от Shikimori, ни от будущих источников.

### `core/models.py`

Содержит универсальные структуры:

- `SourceSearchHit` — один результат поиска конкретного источника;
- `SourceSearchPage` — страница результатов конкретного источника;
- `SearchCandidate` — уже объединённый поисковый результат нескольких источников;
- `SearchPage` — страница универсального поисковика;
- `PersonCredit` — человек и его роли;
- `AnimeRecord` — нормализованный ответ одного источника;
- `AggregatedAnime` — итоговая объединённая карточка.

Источники должны переводить свои собственные JSON/GraphQL/XML ответы в эти модели.

### `core/contracts.py`

Здесь находится интерфейс `AnimeSource`.

Каждый источник должен реализовать только два действия:

```python
async def search(query, page, limit) -> SourceSearchPage
async def get_details(candidate) -> AnimeRecord | None
```

Сам `SearchService` не знает, Shikimori это, AniList, AniDB или другой источник.

---

# Поисковый сервис

Файл:

```text
services/search.py
```

`SearchService` получает список объектов, которые соответствуют контракту `AnimeSource`, и выполняет поиск по ним параллельно.

Схема:

```text
/anime slime
      │
      ▼
SearchService
      │
      ├── Source A.search(...)
      ├── Source B.search(...)
      ├── Source C.search(...)
      └── ...
      │
      ▼
объединение результатов
      │
      ▼
SearchCandidate[]
```

`search.py` **не импортирует пакет `sources`** и ничего не знает о GraphQL Shikimori.

## Как объединяются одинаковые результаты

Сначала используется общий внешний ID, если он доступен. Сейчас приоритет отдаётся MAL ID.

Если общего ID нет, используется нормализованная комбинация:

```text
название + год
```

Например два источника могут вернуть:

```text
Shikimori:
That Time I Got Reincarnated as a Slime
MAL: 37430

AniList:
Tensei shitara Slime Datta Ken
MAL: 37430
```

Поисковик должен превратить их в один `SearchCandidate`, внутри которого будут ссылки на обе базы.

## Ошибка одного источника

Если один источник упал, это не должно ломать весь поиск.

`SearchService` собирает ошибки отдельно, а рабочие источники продолжают возвращать результаты.

---

# Агрегатор

Файл:

```text
services/aggregator.py
```

После того как пользователь выбрал один `SearchCandidate`, бот передаёт его агрегатору.

Схема:

```text
SearchCandidate
      │
      ▼
AnimeAggregator
      │
      ├── Source A.get_details(candidate)
      ├── Source B.get_details(candidate)
      ├── Source C.get_details(candidate)
      └── ...
      │
      ▼
AnimeRecord[]
      │
      ▼
AggregatedAnime
      │
      ▼
Telegram rich message
```

Агрегатор тоже не зависит от конкретной базы данных.

Он объединяет:

- названия;
- синонимы;
- внешние ID;
- тип;
- статус;
- рейтинг;
- количество серий;
- длительность;
- даты показа;
- оценки каждого источника;
- жанры;
- студии;
- лицензиатов;
- описания;
- постеры;
- ссылки;
- авторов и команду;
- сэйю.

Оценки разных сайтов не смешиваются в одно число. Например:

```text
Оценки: Shikimori: 8.15; AniList: 82
```

Описания тоже могут храниться отдельно по источникам.

---

# Источники

Конкретные базы находятся только в:

```text
sources/
```

Сейчас:

```text
sources/shikimori.py
```

В этом файле находятся только вещи, относящиеся к Shikimori:

- URL GraphQL API;
- GraphQL-запросы;
- ограничения API;
- преобразование статусов и типов Shikimori;
- обработка `poster`;
- получение людей и ролей;
- преобразование ответа Shikimori в `SourceSearchHit`;
- преобразование подробного ответа в `AnimeRecord`;
- поиск подходящего Shikimori ID по универсальному `SearchCandidate`.

Telegram-логики внутри источника быть не должно.

## Реестр источников

Файл:

```text
sources/registry.py
```

Это единственное место, где перечисляются включённые адаптеры.

Сейчас:

```python
return (ShikimoriSource(),)
```

Когда появится AniList, станет примерно так:

```python
return (
    ShikimoriSource(),
    AniListSource(),
)
```

Сам поисковик при этом менять не потребуется.

---

# Как добавить новый источник

Допустим, добавляется AniList.

Создаётся:

```text
sources/anilist.py
```

Адаптер должен реализовать:

```python
class AniListSource:
    name = "AniList"

    async def search(self, query, *, page, limit):
        ...

    async def get_details(self, candidate):
        ...
```

`search()` возвращает `SourceSearchPage`.

Каждый результат внутри него — `SourceSearchHit`.

`get_details()` возвращает `AnimeRecord`.

После этого источник добавляется только в:

```text
sources/registry.py
```

`services/search.py`, `services/aggregator.py` и Telegram-бот не должны требовать специальных веток вида:

```python
if source == "anilist":
    ...
```

Если такая проверка начинает появляться, значит источник недостаточно хорошо изолирован адаптером.

---

# Telegram-слой

Файлы:

```text
bots/common.py
bots/official.py
bots/tgapi.py
```

## `bots/common.py`

Здесь находятся:

- команды;
- callback handlers;
- поисковые сессии;
- временные карточки `AggregatedAnime`;
- форматирование универсальной модели в Telegram;
- rich messages;
- пагинация;
- fallback на обычные сообщения.

Он не работает с GraphQL-полями источников.

## `bots/official.py`

Запускает общий бот через официальный:

```text
https://api.telegram.org
```

## `bots/tgapi.py`

Запускает тот же бот через кастомный/self-hosted `telegram-bot-api`.

Бизнес-логика у этих двух режимов одна.

---

# Rich messages

Подробные карточки используют `sendRichMessage`.

В основной карточке можно показывать:

- постер прямо внутри сообщения;
- обычный текст;
- кликабельные callback-ссылки внутри текста.

Пример:

```text
О моём перерождении в слизь

Тип: TV
Статус: вышло
...

Подробная информация
Описание — нажмите, чтобы открыть
Все названия — нажмите, чтобы открыть
Авторы и команда — нажмите, чтобы открыть
Сэйю — нажмите, чтобы открыть
```

Сами названия разделов реализованы как rich callback buttons с `style="link"`.

После нажатия бот редактирует текущее сообщение.

В открытых разделах используются обычные inline-кнопки:

```text
[ ← Назад ]
```

Если раздел слишком длинный:

```text
[ ← Назад ]
[ ◀️ ] [ 1/2 ] [ ▶️ ]
```

---

# Постеры

Постеры хранятся в универсальном поле:

```python
AggregatedAnime.posters
```

Каждый источник сам решает, какой URL считать лучшим.

Для Shikimori сейчас используется приоритет:

```text
originalUrl
↓
main2xUrl
↓
mainUrl
↓
preview2xUrl
↓
previewUrl
```

Разные размеры одного и того же постера не должны отображаться как разные обложки.

Если агрегатор получит реальные разные постеры из разных источников, Telegram-слой может вывести их через rich slideshow.

---

# Поиск и пагинация

У бота нет общего ограничения вида «показывать только первые 5 результатов».

Каждый источник получает:

```python
query
page
limit
```

Сам источник применяет собственные API-ограничения.

Например Shikimori разрешает до 50 элементов на запрос, но умеет `page`, поэтому бот может листать выдачу дальше.

В Telegram сейчас показывается по 10 результатов на страницу.

```text
[ Anime 1 ]
[ Anime 2 ]
...
[ Anime 10 ]

[ ◀️ ] [ Стр. 2 ] [ ▶️ ]
```

Поисковые callback'и не содержат ID Shikimori. Они используют временный токен поисковой сессии и индекс универсального `SearchCandidate`.

---

# Временные сессии

Пока состояние хранится в RAM процесса.

Есть два вида временных данных:

- поисковые сессии;
- уже собранные `AggregatedAnime` для переключения разделов.

Это означает, что после перезапуска бота старые inline/rich callback'и могут устареть.

Для текущей стадии проекта это нормально. Позже этот слой можно вынести в Redis/SQLite/PostgreSQL без изменения источников.

---

# Установка

Требуется:

- Python 3.11+;
- `python3-venv`;
- `tmux` для `start.sh`;
- Telegram bot token.

На Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip tmux git
```

Клонирование:

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Создай конфиг:

```bash
cp .env.example .env
nano .env
```

Минимум:

```env
BOT_TOKEN=123456:your_bot_token
```

После этого:

```bash
./start.sh
```

---

# `.env`

Пример:

```env
BOT_TOKEN=

TELEGRAM_BOT_API_URL=
TELEGRAM_BOT_API_LOCAL=false

SHIKIMORI_API_URL=https://shikimori.io/api/graphql
SHIKIMORI_SITE_URL=https://shikimori.io
```

## Официальный Telegram Bot API

```env
TELEGRAM_BOT_API_URL=
```

Запускается:

```text
bots.official
```

## Self-hosted Telegram Bot API

```env
TELEGRAM_BOT_API_URL=http://127.0.0.1:8081
TELEGRAM_BOT_API_LOCAL=true
```

Запускается:

```text
bots.tgapi
```

`TELEGRAM_BOT_API_LOCAL=true` нужен только если сам `telegram-bot-api` запущен с `--local`.

---

# `start.sh`

Скрипт:

1. проверяет `python3`;
2. проверяет `tmux`;
3. создаёт `.venv`;
4. восстанавливает `pip`, если его нет;
5. устанавливает `requirements.txt`;
6. выполняет `pip check`;
7. проверяет Python imports;
8. проверяет `.env` и `BOT_TOKEN`;
9. выбирает официальный или custom Telegram transport;
10. запускает бот в tmux.

Если бот уже работает:

```text
Bot is already running in tmux session 'anime-db-bot'.
Restart the bot? [y/N]:
```

`y`, `yes`, `д`, `да` — перезапустить.

Другой ответ — оставить текущий экземпляр.

---

# tmux и логи

Подключиться к процессу:

```bash
tmux attach -t anime-db-bot
```

Выйти из tmux, не останавливая бот:

```text
Ctrl+B
D
```

Логи:

```bash
tail -f logs/bot.log
```

Последние строки:

```bash
tail -n 100 logs/bot.log
```

---

# Обновление

```bash
cd anime-db-bot
git pull
./start.sh
```

Если бот уже работает — ответить `y` на предложение перезапуска.

---

# Текущие зависимости

Основные библиотеки:

- `aiogram` — Telegram Bot API;
- `httpx` — HTTP/GraphQL запросы к источникам;
- `python-dotenv` — `.env`.

---

# Планируемые источники

Архитектура рассчитана на постепенное подключение:

- AniList — расписание выхода эпизодов, ID и дополнительная метаинформация;
- AniDB — более глубокая техническая метаинформация;
- AnimeThemes — OP/ED, исполнители и видео;
- SkipDB — тайминги opening / recap / ending / preview;
- другие базы при необходимости.

Каждый новый источник должен оставаться отдельным модулем в `sources/`.

---

# Главный принцип проекта

```text
Источник знает только свой API.
Поиск знает только общий контракт.
Агрегатор знает только нормализованные модели.
Telegram знает только итоговую AggregatedAnime.
```

Это позволяет добавлять, отключать или переписывать отдельные базы без переделки всего бота.
