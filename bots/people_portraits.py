from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from core.models import AggregatedAnime, PersonCredit

PEOPLE_SECTIONS = {"staff", "voices"}
SECTION_TITLES = {
    "staff": "Авторы и команда",
    "voices": "Сэйю / актёры озвучки",
}

_INSTALLED = False
_LAZY_VOICE_DONE: set[str] = set()
_LAZY_VOICE_TASKS: dict[str, asyncio.Task[None]] = {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = " ".join((value or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _section_mapping(anime: AggregatedAnime, section: str) -> dict[str, list[PersonCredit]]:
    if section == "staff":
        return anime.staff_by_source
    if section == "voices":
        return anime.voices_by_source
    return {}


def _all_people(anime: AggregatedAnime, section: str) -> list[PersonCredit]:
    if section == "staff":
        return anime.staff
    if section == "voices":
        return anime.voices
    return []


def _portrait_urls(
    person: PersonCredit,
    *,
    source: str | None = None,
    source_order: list[str] | None = None,
) -> list[str]:
    if source is not None:
        return _dedupe(list(person.portraits.get(source, [])))

    result: list[str] = []
    seen_sources: set[str] = set()
    for source_name in source_order or []:
        seen_sources.add(source_name)
        result.extend(person.portraits.get(source_name, []))
    for source_name, urls in person.portraits.items():
        if source_name not in seen_sources:
            result.extend(urls)
    return _dedupe(result)


def _portrait_source_names(
    person: PersonCredit,
    source_order: list[str],
) -> list[str]:
    available = {
        source
        for source, urls in person.portraits.items()
        if _dedupe(list(urls or []))
    }
    ordered = [source for source in source_order if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _sources_with_portraits(anime: AggregatedAnime, section: str) -> list[str]:
    mapping = _section_mapping(anime, section)
    available: set[str] = set()
    for source, people in mapping.items():
        if any(_portrait_urls(person, source=source) for person in people):
            available.add(source)

    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _people_for_scope(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
) -> list[PersonCredit]:
    if source is None:
        return _all_people(anime, section)
    return _section_mapping(anime, section).get(source, [])


def _people_state(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
) -> tuple[list[PersonCredit], list[PersonCredit]]:
    people = _people_for_scope(anime, section, source)
    without: list[PersonCredit] = []
    with_portraits: list[PersonCredit] = []
    for person in people:
        urls = _portrait_urls(
            person,
            source=source,
            source_order=anime.sources,
        )
        if urls:
            with_portraits.append(person)
        else:
            without.append(person)
    return without, with_portraits


def _person_line(person: PersonCredit) -> str:
    roles = ", ".join(person.roles) if person.roles else "роль не указана"
    return f"• {person.name} — {roles}"


def _page_text(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
    page: int,
) -> tuple[str, list[str], int, int, int]:
    without, with_portraits = _people_state(anime, section, source)
    total = len(without) + len(with_portraits)
    max_page = len(with_portraits)
    page = max(0, min(page, max_page))

    title = SECTION_TITLES[section]
    if source:
        title += f" — {source}"

    if page == 0:
        lines = [f"{title}:", "", "Без портрета:"]
        if without:
            lines.extend(_person_line(person) for person in without)
        else:
            lines.append("Нет.")
        return "\n".join(lines), [], len(without), total, page

    person = with_portraits[page - 1]
    roles = ", ".join(person.roles) if person.roles else "роль не указана"
    portrait_sources = _portrait_source_names(person, anime.sources)
    urls = _portrait_urls(
        person,
        source=source,
        source_order=anime.sources,
    )

    lines = [
        f"{title}:",
        "",
        person.name,
        f"Роли: {roles}",
    ]
    if portrait_sources:
        lines.append("Портреты: " + ", ".join(portrait_sources))

    shown = len(without) + page
    return "\n".join(lines), urls, shown, total, page


def _portrait_html(urls: list[str]) -> str:
    urls = _dedupe(urls)[:20]
    if not urls:
        return ""
    images = "".join(
        f'<img src="{html.escape(url, quote=True)}"/>'
        for url in urls
    )
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def _rich(common: Any, text: str, urls: list[str]) -> InputRichMessage:
    return InputRichMessage(
        html=_portrait_html(urls) + common._plain_text_to_rich_html(text)
    )


def _page_callback(
    token: str,
    section: str,
    source_index: int | None,
    page: int,
) -> str:
    if source_index is None:
        return f"av:{token}:{section}:{page}"
    return f"as:{token}:{section}:{source_index}:{page}"


def _source_rows(
    common: Any,
    token: str,
    anime: AggregatedAnime,
    section: str,
    selected_source_index: int | None,
) -> list[list[InlineKeyboardButton]]:
    sources = common._source_section_sources(anime, section)
    if not sources:
        return []

    all_label = common.ALL_SOURCE_LABELS[section]
    rows: list[list[InlineKeyboardButton]] = [[
        InlineKeyboardButton(
            text=("✓ " + all_label) if selected_source_index is None else all_label,
            callback_data=f"av:{token}:{section}:0",
        )
    ]]

    buttons = [
        InlineKeyboardButton(
            text=("✓ " + source) if selected_source_index == index else source,
            callback_data=f"as:{token}:{section}:{index}:0",
        )
        for index, source in enumerate(sources)
    ]
    rows.extend(buttons[index:index + 2] for index in range(0, len(buttons), 2))
    return rows


def _keyboard(
    common: Any,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int | None,
    page: int,
    shown: int,
    total: int,
    max_page: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=_page_callback(token, section, source_index, page - 1),
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"Показано {shown}/{total}",
            callback_data="noop",
        )
    )
    if page < max_page:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=_page_callback(token, section, source_index, page + 1),
            )
        )
    rows.append(nav)

    rows.extend(
        _source_rows(
            common,
            token,
            anime,
            section,
            selected_source_index=source_index,
        )
    )

    rows.append([
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"av:{token}:main:0",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ensure_lazy_voices(
    common: Any,
    token: str,
    anime: AggregatedAnime,
    message: Message,
) -> None:
    """Populate deferred Shikimori seiyuu once for this anime-card session."""
    if token in _LAZY_VOICE_DONE:
        return

    running = _LAZY_VOICE_TASKS.get(token)
    if running is not None:
        await running
        return

    async def load() -> None:
        try:
            source = next(
                (
                    item
                    for item in common.SOURCES
                    if item.name == "Shikimori" and hasattr(item, "load_voices")
                ),
                None,
            )
            if source is None:
                return

            mal_id = str(anime.external_ids.get("mal") or "").strip()
            shikimori_id = str(anime.external_ids.get("shikimori") or "").strip()
            if not mal_id.isdigit() or not shikimori_id.isdigit():
                return

            try:
                await message.edit_text(
                    text="Загружаю сэйю Shikimori…",
                    reply_markup=None,
                )
            except Exception:
                logging.debug(
                    "Could not show lazy Shikimori seiyuu loading state",
                    exc_info=True,
                )

            voices = await source.load_voices(mal_id, anime.external_ids)
            common.AGGREGATOR.merge_people_source(
                anime,
                source_name="Shikimori",
                people=voices,
                section="voices",
            )
            logging.info(
                "Lazy Shikimori seiyuu loaded for MAL %s: %d people",
                mal_id,
                len(voices),
            )
        except Exception:
            # AniList (and any future already-loaded sources) remain usable.
            # A new anime-card session can retry a temporary Shikimori failure.
            logging.exception("Lazy Shikimori seiyuu load failed")
        finally:
            _LAZY_VOICE_DONE.add(token)

    task = asyncio.create_task(load())
    _LAZY_VOICE_TASKS[token] = task
    try:
        await task
    finally:
        _LAZY_VOICE_TASKS.pop(token, None)


async def _edit_people_view(
    common: Any,
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int | None,
    page: int,
) -> None:
    if section == "voices":
        await _ensure_lazy_voices(common, token, anime, message)

    sources = common._source_section_sources(anime, section)
    source: str | None = None
    if source_index is not None:
        if source_index < 0 or source_index >= len(sources):
            raise ValueError("Portrait source index is out of range")
        source = sources[source_index]

    without, with_portraits = _people_state(anime, section, source)
    max_page = len(with_portraits)
    page = max(0, min(int(page), max_page))
    text, urls, shown, total, page = _page_text(
        anime,
        section,
        source,
        page,
    )
    keyboard = _keyboard(
        common,
        token,
        anime,
        section,
        source_index,
        page,
        shown,
        total,
        max_page,
    )

    try:
        await message.edit_text(
            rich_message=_rich(common, text, urls),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich portrait view edit failed; falling back to standard text edit"
        )
        await message.edit_text(
            text=common._split_text(text, common.STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=keyboard,
        )


def install(common: Any) -> None:
    """Install portrait-aware people views into bots.common.

    The existing title/description/link handlers stay untouched. Staff and
    seiyuu reuse the same av:/as: callback namespaces, so source selection and
    portrait pagination remain part of one anime-card session. Expensive
    Shikimori character/seiyuu data is loaded only on first entry to voices.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    original_source_section_sources = common._source_section_sources
    original_edit_anime_view = common._edit_anime_view
    original_edit_source_section_view = common._edit_source_section_view

    def source_section_sources(anime: AggregatedAnime, section: str) -> list[str]:
        if section in PEOPLE_SECTIONS:
            return _sources_with_portraits(anime, section)
        return original_source_section_sources(anime, section)

    async def edit_anime_view(
        message: Message,
        token: str,
        anime: AggregatedAnime,
        section: str,
        page: int,
    ) -> None:
        if section in PEOPLE_SECTIONS:
            await _edit_people_view(
                common,
                message,
                token,
                anime,
                section,
                source_index=None,
                page=page,
            )
            return
        await original_edit_anime_view(message, token, anime, section, page)

    async def edit_source_section_view(
        message: Message,
        token: str,
        anime: AggregatedAnime,
        section: str,
        source_index: int,
        page: int,
    ) -> None:
        if section in PEOPLE_SECTIONS:
            await _edit_people_view(
                common,
                message,
                token,
                anime,
                section,
                source_index=source_index,
                page=page,
            )
            return
        await original_edit_source_section_view(
            message,
            token,
            anime,
            section,
            source_index,
            page,
        )

    common._source_section_sources = source_section_sources
    common._edit_anime_view = edit_anime_view
    common._edit_source_section_view = edit_source_section_view
    _INSTALLED = True
