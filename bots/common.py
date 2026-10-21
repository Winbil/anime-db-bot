from __future__ import annotations

import html
import logging
import os
import secrets
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from dotenv import load_dotenv

from bots.session_store import ExpiringSessionStore
from core.models import AggregatedAnime, SearchCandidate, SearchPage
from search.registry import get_search_providers
from services.aggregator import AnimeAggregator
from services.search import SearchService
from sources.registry import get_sources

load_dotenv()

STANDARD_MESSAGE_LIMIT = 3900
RICH_MESSAGE_LIMIT = 32000
SEARCH_PAGE_SIZE = 10
MAX_SEARCH_SESSIONS = 200
MAX_ANIME_SESSIONS = 200

SEARCH_PROVIDERS = get_search_providers()
SOURCES = get_sources()
SEARCH_SERVICE = SearchService(SEARCH_PROVIDERS)
AGGREGATOR = AnimeAggregator(SOURCES)

SECTION_LABELS = {
    "main": "Основное",
    "titles": "Названия",
    "description": "Описание",
    "links": "Ссылки",
    "staff": "Команда",
    "voices": "Сэйю",
}
SOURCE_SELECTABLE_SECTIONS = {"titles", "staff", "voices"}
ALL_SOURCE_LABELS = {
    "titles": "Все названия",
    "staff": "Вся команда",
    "voices": "Все сэйю",
}


@dataclass(slots=True)
class SearchSession:
    query: str
    pages: dict[int, SearchPage] = field(default_factory=dict)


SEARCH_SESSIONS: ExpiringSessionStore[SearchSession] = ExpiringSessionStore(
    max_entries=MAX_SEARCH_SESSIONS,
)
ANIME_SESSIONS: ExpiringSessionStore[AggregatedAnime] = ExpiringSessionStore(
    max_entries=MAX_ANIME_SESSIONS,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_bot(use_custom_api: bool) -> Bot:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and add the bot token."
        )

    if not use_custom_api:
        return Bot(token=token)

    api_url = os.getenv("TELEGRAM_BOT_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise RuntimeError(
            "TELEGRAM_BOT_API_URL is empty, but the tg-bot-api launcher was selected."
        )

    api = TelegramAPIServer.from_base(
        api_url,
        is_local=_env_bool("TELEGRAM_BOT_API_LOCAL", False),
    )
    return Bot(token=token, session=AiohttpSession(api=api))


def _split_text(text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text:
        return ["Нет данных."]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    if text:
        chunks.append(text)
    return chunks


def _plain_text_to_rich_html(text: str) -> str:
    paragraphs: list[str] = []
    for paragraph in text.split("\n\n"):
        escaped = html.escape(paragraph).replace("\n", "<br>")
        if escaped:
            paragraphs.append(f"<p>{escaped}</p>")
    return "".join(paragraphs)


def _poster_html(anime: AggregatedAnime) -> str:
    urls = anime.posters[:50]
    if not urls:
        return ""
    images = "".join(
        f'<img src="{html.escape(url, quote=True)}"/>'
        for url in urls
    )
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def _rich(text: str) -> InputRichMessage:
    return InputRichMessage(html=_plain_text_to_rich_html(text))


def _main_rich(token: str, anime: AggregatedAnime, text: str) -> InputRichMessage:
    links = (
        "<p><b>Подробная информация</b><br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:description:0">Описание</tg-button>'
        " — выбрать источник<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:titles:0">Все названия</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:staff:0">Авторы и команда</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:voices:0">Сэйю</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:links:0">Ссылки</tg-button>'
        " — выбрать базу</p>"
    )
    return InputRichMessage(
        html=_poster_html(anime) + _plain_text_to_rich_html(text) + links
    )


async def _send_standard_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    chunks = _split_text(text, STANDARD_MESSAGE_LIMIT)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _format_number(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:,}".replace(",", " ")


def _format_people(title: str, people) -> str:
    if not people:
        return f"{title}:\nНет данных."
    lines = [f"{title}:"]
    for person in people:
        roles = ", ".join(person.roles) if person.roles else "роль не указана"
        lines.append(f"• {person.name} — {roles}")
    return "\n".join(lines)


def _format_titles(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    source: str | None = None,
) -> str:
    title = f"Названия — {source}:" if source else "Названия:"
    lines = [title]
    labels = {
        "russian": "Русское",
        "romaji": "Оригинальное / romaji",
        "english": "English",
        "japanese": "日本語",
        "licensed_ru": "Лицензионное RU",
    }
    seen_titles: set[str] = set()
    for key in ("russian", "romaji", "english", "japanese", "licensed_ru"):
        value = (titles_map.get(key) or "").strip()
        if value and value.casefold() not in seen_titles:
            seen_titles.add(value.casefold())
            lines.append(f"• {labels[key]}: {value}")

    synonyms = [
        value
        for value in _dedupe_strings(synonyms_values)
        if value.casefold() not in seen_titles
    ]
    if synonyms:
        lines.append("• Синонимы: " + "; ".join(synonyms))

    if len(lines) == 1:
        lines.append("Нет данных.")
    return "\n".join(lines)


def _append_block(target: list[str], title: str, lines: list[str]) -> None:
    lines = [line for line in lines if line]
    if not lines:
        return
    if target:
        target.append("")
    target.append(f"{title}:")
    target.extend(lines)


def _ordered_mapping_items(
    mapping: dict[str, object],
    source_order: list[str],
) -> list[tuple[str, object]]:
    result: list[tuple[str, object]] = []
    seen: set[str] = set()
    for source in source_order:
        if source in mapping:
            result.append((source, mapping[source]))
            seen.add(source)
    for source, value in mapping.items():
        if source not in seen:
            result.append((source, value))
    return result


def _source_section_sources(anime: AggregatedAnime, section: str) -> list[str]:
    if section == "titles":
        available = {
            source
            for source in set(anime.titles_by_source) | set(anime.synonyms_by_source)
            if anime.titles_by_source.get(source) or anime.synonyms_by_source.get(source)
        }
    elif section == "staff":
        available = {
            source for source, people in anime.staff_by_source.items() if people
        }
    elif section == "voices":
        available = {
            source for source, people in anime.voices_by_source.items() if people
        }
    else:
        return []

    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _source_section_text(
    anime: AggregatedAnime,
    section: str,
    source: str,
) -> str:
    if section == "titles":
        return _format_titles(
            anime.titles_by_source.get(source, {}),
            anime.synonyms_by_source.get(source, []),
            source=source,
        )
    if section == "staff":
        return _format_people(
            f"Авторы и команда — {source}",
            anime.staff_by_source.get(source, []),
        )
    if section == "voices":
        return _format_people(
            f"Сэйю / актёры озвучки — {source}",
            anime.voices_by_source.get(source, []),
        )
    return "Нет данных."


def _anime_sections(anime: AggregatedAnime) -> dict[str, str]:
    total = anime.episodes_total or 0
    aired = anime.episodes_aired or 0
    episodes = f"{aired}/{total}" if total else str(aired or "—")

    main = [anime.title]
    basic: list[str] = []
    if anime.kind:
        basic.append(f"Тип: {anime.kind}")
    if anime.status:
        basic.append(f"Статус: {anime.status}")
    basic.append(f"Серии: {episodes}")
    if anime.duration_minutes:
        basic.append(f"Длительность серии: {anime.duration_minutes} мин.")
    if anime.rating:
        basic.append(f"Возрастной рейтинг: {anime.rating}")
    _append_block(main, "Основное", basic)

    release: list[str] = []
    if anime.season:
        release.append(f"Сезон: {anime.season}")
    if anime.aired_on or anime.released_on:
        release.append(
            "Начало/Конец показа: "
            f"{anime.aired_on or '—'}/{anime.released_on or '—'}"
        )
    if anime.next_episode_at:
        release.append(f"Следующая серия: {anime.next_episode_at}")
    if anime.broadcasts:
        release.append(f"Расписание: {', '.join(anime.broadcasts)}")
    _append_block(main, "Выход", release)

    production: list[str] = []
    if anime.source_materials:
        production.append(f"Первоисточник: {', '.join(anime.source_materials)}")
    if anime.genres:
        production.append(f"Жанры: {', '.join(anime.genres)}")
    if anime.studios:
        production.append(f"Студии: {', '.join(anime.studios)}")
    if anime.licensors:
        production.append(f"Лицензиаты: {', '.join(anime.licensors)}")
    if anime.franchise:
        production.append(f"Франшиза: {anime.franchise}")
    _append_block(main, "Производство", production)

    audience: list[str] = []
    if anime.score_average is not None:
        audience.append(
            f"Средняя оценка: {anime.score_average:g} "
            f"(источников: {anime.score_sources_count})"
        )
    for source, score in _ordered_mapping_items(anime.scores, anime.sources):
        audience.append(f"{source}: {float(score):g}")
    if anime.rank:
        audience.append(f"Рейтинг: #{anime.rank}")
    if anime.popularity_rank:
        audience.append(f"Популярность: #{anime.popularity_rank}")
    if anime.list_users is not None:
        audience.append(f"В списках пользователей: {_format_number(anime.list_users)}")
    if anime.scoring_users is not None:
        audience.append(f"Поставили оценку: {_format_number(anime.scoring_users)}")
    if anime.favorites is not None:
        audience.append(f"В избранном: {_format_number(anime.favorites)}")
    _append_block(main, "Оценка и популярность", audience)

    source_lines: list[str] = []
    if anime.sources:
        source_lines.append(f"Базы данных: {', '.join(anime.sources)}")
    if anime.external_ids:
        ids = " | ".join(
            f"{name.upper()}: {value}" for name, value in anime.external_ids.items()
        )
        source_lines.append(f"ID: {ids}")
    if anime.errors:
        source_lines.append("Недоступны: " + ", ".join(anime.errors))
    _append_block(main, "Источники", source_lines)

    description_text = (
        "Описание:\nВыбери источник кнопкой ниже."
        if anime.descriptions
        else "Описание:\nНет доступных описаний."
    )
    links_text = (
        "Ссылки:\nВыбери базу кнопкой ниже."
        if anime.urls
        else "Ссылки:\nНет доступных ссылок."
    )

    return {
        "main": "\n".join(main),
        "titles": _format_titles(anime.titles, anime.synonyms),
        "description": description_text,
        "links": links_text,
        "staff": _format_people("Авторы и команда", anime.staff),
        "voices": _format_people("Сэйю / актёры озвучки", anime.voices),
    }


def _view_pages(anime: AggregatedAnime, section: str) -> list[str]:
    return _split_text(
        _anime_sections(anime).get(section) or "Нет данных.",
        RICH_MESSAGE_LIMIT,
    )


def _description_sources(anime: AggregatedAnime) -> list[str]:
    return [
        source
        for source, _ in _ordered_mapping_items(anime.descriptions, anime.sources)
    ]


def _description_selection_rows(
    token: str,
    anime: AggregatedAnime,
) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(
            text=source,
            callback_data=f"ad:{token}:{index}:0",
        )
        for index, source in enumerate(_description_sources(anime))
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def _source_section_selection_rows(
    token: str,
    anime: AggregatedAnime,
    section: str,
    *,
    selected_source_index: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    sources = _source_section_sources(anime, section)
    if not sources:
        return []

    all_label = ALL_SOURCE_LABELS[section]
    rows: list[list[InlineKeyboardButton]] = [[
        InlineKeyboardButton(
            text=("✓ " + all_label) if selected_source_index is None else all_label,
            callback_data=f"av:{token}:{section}:0",
        )
    ]]

    source_buttons = [
        InlineKeyboardButton(
            text=("✓ " + source) if selected_source_index == index else source,
            callback_data=f"as:{token}:{section}:{index}:0",
        )
        for index, source in enumerate(sources)
    ]
    rows.extend(
        source_buttons[index:index + 2]
        for index in range(0, len(source_buttons), 2)
    )
    return rows


def _link_rows(anime: AggregatedAnime) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(text=source, url=str(url))
        for source, url in _ordered_mapping_items(anime.urls, anime.sources)
        if str(url).strip()
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def _navigation_keyboard(
    token: str,
    anime: AggregatedAnime,
    current_section: str,
    page: int,
    page_count: int,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []

    if current_section == "description":
        rows.extend(_description_selection_rows(token, anime))
    elif current_section == "links":
        rows.extend(_link_rows(anime))
    elif current_section in SOURCE_SELECTABLE_SECTIONS:
        rows.extend(
            _source_section_selection_rows(
                token,
                anime,
                current_section,
                selected_source_index=None,
            )
        )

    if current_section != "main":
        rows.append([
            InlineKeyboardButton(
                text="← Назад",
                callback_data=f"av:{token}:main:0",
            )
        ])

    if page_count > 1 and current_section not in {"description", "links"}:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"av:{token}:{current_section}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{page_count}",
            callback_data="noop",
        ))
        if page + 1 < page_count:
            nav.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"av:{token}:{current_section}:{page + 1}",
            ))
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _description_keyboard(
    token: str,
    source_index: int,
    page: int,
    page_count: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"ad:{token}:{source_index}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{page_count}",
            callback_data="noop",
        ))
        if page + 1 < page_count:
            nav.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"ad:{token}:{source_index}:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(
            text="← Источники",
            callback_data=f"av:{token}:description:0",
        ),
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"av:{token}:main:0",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _source_section_keyboard(
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int,
    page: int,
    page_count: int,
) -> InlineKeyboardMarkup:
    rows = _source_section_selection_rows(
        token,
        anime,
        section,
        selected_source_index=source_index,
    )

    rows.append([
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"av:{token}:main:0",
        )
    ])

    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"as:{token}:{section}:{source_index}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{page_count}",
            callback_data="noop",
        ))
        if page + 1 < page_count:
            nav.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"as:{token}:{section}:{source_index}:{page + 1}",
            ))
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _fallback_main_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Описание",
                callback_data=f"av:{token}:description:0",
            ),
            InlineKeyboardButton(
                text="Названия",
                callback_data=f"av:{token}:titles:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Команда",
                callback_data=f"av:{token}:staff:0",
            ),
            InlineKeyboardButton(
                text="Сэйю",
                callback_data=f"av:{token}:voices:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Ссылки",
                callback_data=f"av:{token}:links:0",
            )
        ],
    ])


def _remember_search(query: str, first_page: SearchPage) -> str:
    token = secrets.token_urlsafe(6)
    SEARCH_SESSIONS[token] = SearchSession(
        query=query,
        pages={first_page.page: first_page},
    )
    return token


def _remember_anime(anime: AggregatedAnime) -> str:
    token = secrets.token_urlsafe(6)
    ANIME_SESSIONS[token] = anime
    return token


def _candidate_button_text(candidate: SearchCandidate) -> str:
    text = f"{candidate.title} ({candidate.year})" if candidate.year else candidate.title
    mal_id = candidate.external_ids.get("mal")
    if mal_id:
        text += f" · MAL {mal_id}"
    return text if len(text) <= 64 else text[:61] + "..."


def _search_keyboard(search_page: SearchPage, token: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=_candidate_button_text(candidate),
            callback_data=f"pick:{token}:{search_page.page}:{index}",
        )]
        for index, candidate in enumerate(search_page.items)
    ]

    nav: list[InlineKeyboardButton] = []
    if search_page.page > 1:
        nav.append(InlineKeyboardButton(
            text="◀️",
            callback_data=f"sp:{token}:{search_page.page - 1}",
        ))
    nav.append(InlineKeyboardButton(
        text=f"Стр. {search_page.page}",
        callback_data="noop",
    ))
    if search_page.has_next:
        nav.append(InlineKeyboardButton(
            text="▶️",
            callback_data=f"sp:{token}:{search_page.page + 1}",
        ))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _search_message(query: str, search_page: SearchPage) -> str:
    text = f"Результаты поиска по запросу «{query}». Выбери нужное аниме:"
    if search_page.errors:
        text += "\n\nНедоступны поисковики: " + ", ".join(search_page.errors)
    return text


def _rich_view(
    token: str,
    anime: AggregatedAnime,
    section: str,
    text: str,
) -> InputRichMessage:
    return _main_rich(token, anime, text) if section == "main" else _rich(text)


async def _send_anime_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str = "main",
    page: int = 0,
) -> None:
    pages = _view_pages(anime, section)
    page = max(0, min(page, len(pages) - 1))
    keyboard = _navigation_keyboard(token, anime, section, page, len(pages))
    text = pages[page]

    try:
        await message.answer_rich(
            _rich_view(token, anime, section, text),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("sendRichMessage failed; falling back to standard sendMessage")
        fallback = _fallback_main_keyboard(token) if section == "main" else keyboard
        await _send_standard_text(message, text, reply_markup=fallback)


async def _edit_anime_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    page: int,
) -> None:
    pages = _view_pages(anime, section)
    page = max(0, min(page, len(pages) - 1))
    keyboard = _navigation_keyboard(token, anime, section, page, len(pages))
    text = pages[page]

    try:
        await message.edit_text(
            rich_message=_rich_view(token, anime, section, text),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich message edit failed; falling back to standard text edit")
        fallback = _fallback_main_keyboard(token) if section == "main" else keyboard
        await message.edit_text(
            text=_split_text(text, STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=fallback,
        )


async def _edit_description_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    source_index: int,
    page: int,
) -> None:
    sources = _description_sources(anime)
    if source_index < 0 or source_index >= len(sources):
        raise ValueError("Description source index is out of range")

    source = sources[source_index]
    description = anime.descriptions[source]
    text = f"Описание — {source}\n\n{description}"
    if source == "MyAnimeList" and anime.background:
        text += f"\n\nДополнительная информация:\n{anime.background}"

    pages = _split_text(text, RICH_MESSAGE_LIMIT)
    page = max(0, min(page, len(pages) - 1))
    keyboard = _description_keyboard(token, source_index, page, len(pages))

    try:
        await message.edit_text(
            rich_message=_rich(pages[page]),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich description edit failed; falling back to standard text edit")
        await message.edit_text(
            text=_split_text(pages[page], STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=keyboard,
        )


async def _edit_source_section_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int,
    page: int,
) -> None:
    sources = _source_section_sources(anime, section)
    if source_index < 0 or source_index >= len(sources):
        raise ValueError("Source section index is out of range")

    source = sources[source_index]
    pages = _split_text(
        _source_section_text(anime, section, source),
        RICH_MESSAGE_LIMIT,
    )
    page = max(0, min(page, len(pages) - 1))
    keyboard = _source_section_keyboard(
        token,
        anime,
        section,
        source_index,
        page,
        len(pages),
    )

    try:
        await message.edit_text(
            rich_message=_rich(pages[page]),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich source section edit failed; falling back to standard text edit")
        await message.edit_text(
            text=_split_text(pages[page], STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=keyboard,
        )


async def _aggregate_and_send(message: Message, candidate: SearchCandidate) -> None:
    mal_id = candidate.external_ids.get("mal")
    if not mal_id:
        await message.answer("У выбранного результата нет MAL ID.")
        return

    try:
        anime = await AGGREGATOR.aggregate(candidate)
    except Exception as exc:
        logging.error(
            "Anime aggregation failed for MAL %s: %s: %s",
            mal_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await message.answer(
            f"Не удалось собрать данные для MAL ID {mal_id} из подключённых источников."
        )
        return

    token = _remember_anime(anime)
    await _send_anime_view(message, token, anime, section="main", page=0)


async def _get_search_page(session: SearchSession, page: int) -> SearchPage:
    if page not in session.pages:
        session.pages[page] = await SEARCH_SERVICE.search(
            session.query,
            page=page,
            page_size=SEARCH_PAGE_SIZE,
        )
    return session.pages[page]


def build_dispatcher(mode_name: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        source_names = ", ".join(source.name for source in SOURCES) or "нет"
        await message.answer(
            "Привет! Это anime-db-bot.\n\n"
            f"Режим Telegram: {mode_name}\n"
            f"Основной поиск: {SEARCH_SERVICE.provider_name}\n"
            f"Источники данных: {source_names}\n\n"
            "После выбора MAL ID бот собирает и объединяет метаданные всех доступных источников без повторений.\n\n"
            "Команды:\n"
            "/anime <название> — общий поиск\n"
            "/search <название> — выбрать конкретные поисковики\n"
            "/ping — проверить, что бот работает"
        )

    @dp.message(Command("ping"))
    async def ping_handler(message: Message) -> None:
        await message.answer("pong")

    @dp.message(Command("anime"))
    async def anime_handler(message: Message, command: CommandObject) -> None:
        query = (command.args or "").strip()
        if not query:
            await message.answer(
                "Использование: /anime <название>\n"
                "Например: /anime о моем перерождении в слизь"
            )
            return

        try:
            search_page = await SEARCH_SERVICE.search(
                query,
                page=1,
                page_size=SEARCH_PAGE_SIZE,
            )
        except Exception as exc:
            logging.error(
                "Search service failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            await message.answer("Не удалось выполнить поиск. Причина записана в лог.")
            return

        if not search_page.items:
            if search_page.errors:
                await message.answer(
                    "Не удалось получить результаты. Недоступны поисковики: "
                    + ", ".join(search_page.errors)
                )
            else:
                await message.answer("Ничего не найдено по этому запросу.")
            return

        if len(search_page.items) == 1 and not search_page.has_next:
            await _aggregate_and_send(message, search_page.items[0])
            return

        token = _remember_search(query, search_page)
        await message.answer(
            _search_message(query, search_page),
            reply_markup=_search_keyboard(search_page, token),
        )

    @dp.callback_query(F.data == "noop")
    async def noop_callback(callback: CallbackQuery) -> None:
        await callback.answer()

    @dp.callback_query(F.data.startswith("sp:"))
    async def search_page_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 3 or not data[2].isdigit():
            await callback.answer("Некорректная страница.", show_alert=True)
            return

        _, token, page_text = data
        session = SEARCH_SESSIONS.get(token)
        if session is None:
            await callback.answer(
                "Этот поиск устарел. Выполни /anime ещё раз.",
                show_alert=True,
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        try:
            search_page = await _get_search_page(session, max(1, int(page_text)))
        except Exception as exc:
            logging.error(
                "Search page failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            await callback.answer("Не удалось загрузить страницу поиска.", show_alert=True)
            return

        if not search_page.items:
            await callback.answer("Больше результатов нет.", show_alert=True)
            return

        await callback.answer()
        await callback.message.edit_text(
            _search_message(session.query, search_page),
            reply_markup=_search_keyboard(search_page, token),
        )

    @dp.callback_query(F.data.startswith("pick:"))
    async def pick_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[2].isdigit() or not data[3].isdigit():
            await callback.answer("Некорректный результат.", show_alert=True)
            return

        _, token, page_text, index_text = data
        session = SEARCH_SESSIONS.get(token)
        if session is None:
            await callback.answer(
                "Этот поиск устарел. Выполни /anime ещё раз.",
                show_alert=True,
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        try:
            search_page = await _get_search_page(session, max(1, int(page_text)))
        except Exception:
            logging.exception("Could not reload search page for selection")
            await callback.answer("Не удалось получить результат поиска.", show_alert=True)
            return

        index = int(index_text)
        if index < 0 or index >= len(search_page.items):
            await callback.answer("Результат больше недоступен.", show_alert=True)
            return

        candidate = search_page.items[index]
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logging.debug("Could not remove search keyboard", exc_info=True)
        await _aggregate_and_send(callback.message, candidate)

    @dp.callback_query(F.data.startswith("ad:"))
    async def description_source_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if (
            len(data) != 4
            or not data[2].isdigit()
            or not data[3].isdigit()
        ):
            await callback.answer("Некорректное описание.", show_alert=True)
            return

        _, token, source_index_text, page_text = data
        anime = ANIME_SESSIONS.get(token)
        if anime is None:
            await callback.answer(
                "Карточка устарела. Выполни поиск ещё раз.",
                show_alert=True,
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        source_index = int(source_index_text)
        if source_index >= len(_description_sources(anime)):
            await callback.answer("Источник описания больше недоступен.", show_alert=True)
            return

        await callback.answer()
        await _edit_description_view(
            callback.message,
            token,
            anime,
            source_index=source_index,
            page=int(page_text),
        )

    @dp.callback_query(F.data.startswith("as:"))
    async def source_section_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if (
            len(data) != 5
            or data[2] not in SOURCE_SELECTABLE_SECTIONS
            or not data[3].isdigit()
            or not data[4].isdigit()
        ):
            await callback.answer("Некорректный источник.", show_alert=True)
            return

        _, token, section, source_index_text, page_text = data
        anime = ANIME_SESSIONS.get(token)
        if anime is None:
            await callback.answer(
                "Карточка устарела. Выполни поиск ещё раз.",
                show_alert=True,
            )
            return
        if callback.message is None:
            await callback.answer()
            return

        sources = _source_section_sources(anime, section)
        source_index = int(source_index_text)
        if source_index >= len(sources):
            await callback.answer("Источник больше недоступен.", show_alert=True)
            return

        await callback.answer()
        await _edit_source_section_view(
            callback.message,
            token,
            anime,
            section,
            source_index,
            int(page_text),
        )

    @dp.callback_query(F.data.startswith("av:"))
    async def anime_view_callback_handler(callback: CallbackQuery) -> None:
        data = (callback.data or "").split(":")
        if len(data) != 4 or not data[3].isdigit():
            await callback.answer("Некорректная команда.", show_alert=True)
            return

        _, token, section, page_text = data
        anime = ANIME_SESSIONS.get(token)
        if anime is None:
            await callback.answer(
                "Карточка устарела. Выполни поиск ещё раз.",
                show_alert=True,
            )
            return
        if section not in SECTION_LABELS:
            await callback.answer("Некорректный раздел.", show_alert=True)
            return
        if callback.message is None:
            await callback.answer()
            return

        await callback.answer()
        await _edit_anime_view(
            callback.message,
            token,
            anime,
            section=section,
            page=int(page_text),
        )

    return dp


async def run_bot(*, use_custom_api: bool, mode_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot mode: %s", mode_name)
    logging.info("Search providers: %s", SEARCH_SERVICE.provider_name)
    logging.info("Metadata sources: %s", ", ".join(source.name for source in SOURCES))

    bot = create_bot(use_custom_api=use_custom_api)
    dp = build_dispatcher(mode_name=mode_name)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
