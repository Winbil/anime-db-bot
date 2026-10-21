from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.constants import ALL_SOURCE_LABELS, STANDARD_MESSAGE_LIMIT
from bots.telegram.card.renderer import plain_text_to_rich_html, split_text
from bots.telegram.card.service import AGGREGATOR, SOURCES
from bots.telegram.card.state import ANIME_SESSIONS
from core.models import AggregatedAnime, PersonCredit

PEOPLE_SECTIONS = {"staff", "voices"}
SECTION_TITLES = {
    "staff": "Авторы и команда",
    "voices": "Сэйю / актёры озвучки",
}

_LAZY_PEOPLE_DONE: ExpiringSessionStore[bool] = ExpiringSessionStore(max_entries=400)
_LAZY_PEOPLE_TASKS: dict[str, asyncio.Task[bool]] = {}


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


def _rich(text: str, urls: list[str]) -> InputRichMessage:
    return InputRichMessage(
        html=_portrait_html(urls) + plain_text_to_rich_html(text)
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
    token: str,
    anime: AggregatedAnime,
    section: str,
    selected_source_index: int | None,
) -> list[list[InlineKeyboardButton]]:
    sources = _sources_with_portraits(anime, section)
    if not sources:
        return []

    all_label = ALL_SOURCE_LABELS[section]
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


async def _ensure_lazy_people(
    token: str,
    anime: AggregatedAnime,
    message: Message,
    section: str,
) -> None:
    """Load expensive person lists only when their UI section is opened."""
    key = f"{token}:{section}"
    if _LAZY_PEOPLE_DONE.get(key):
        return

    running = _LAZY_PEOPLE_TASKS.get(key)
    if running is not None:
        if await running:
            _LAZY_PEOPLE_DONE[key] = True
        return

    method_name = "load_staff" if section == "staff" else "load_voices"
    mapping = _section_mapping(anime, section)
    loaders: list[tuple[Any, Any]] = []
    for source in SOURCES:
        loader = getattr(source, method_name, None)
        if callable(loader) and source.name not in mapping:
            loaders.append((source, loader))

    if not loaders:
        _LAZY_PEOPLE_DONE[key] = True
        return

    async def load() -> bool:
        try:
            loading_text = (
                "Загружаю авторов, команду и портреты…"
                if section == "staff"
                else "Загружаю сэйю и портреты…"
            )
            try:
                await message.edit_text(text=loading_text, reply_markup=None)
            except Exception:
                logging.debug(
                    "Could not show lazy people loading state",
                    exc_info=True,
                )

            mal_id = str(anime.external_ids.get("mal") or "").strip()
            if not mal_id.isdigit():
                return True

            async def load_source(source: Any, loader: Any):
                people = await loader(mal_id, anime.external_ids)
                return source, people

            results = await asyncio.gather(
                *(load_source(source, loader) for source, loader in loaders),
                return_exceptions=True,
            )

            success = True
            for result in results:
                if isinstance(result, Exception):
                    success = False
                    logging.error(
                        "Lazy %s source load failed: %s",
                        section,
                        result,
                        exc_info=(type(result), result, result.__traceback__),
                    )
                    continue

                source, people = result
                AGGREGATOR.merge_people_source(
                    anime,
                    source_name=source.name,
                    people=people,
                    section=section,
                )
                logging.info(
                    "Lazy %s loaded from %s for MAL %s: %d people",
                    section,
                    source.name,
                    mal_id,
                    len(people),
                )
            return success
        except Exception:
            logging.exception("Lazy %s loading failed", section)
            return False

    task = asyncio.create_task(load())
    _LAZY_PEOPLE_TASKS[key] = task
    try:
        if await task:
            _LAZY_PEOPLE_DONE[key] = True
    finally:
        _LAZY_PEOPLE_TASKS.pop(key, None)


async def _edit_people_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int | None,
    page: int,
) -> None:
    await _ensure_lazy_people(token, anime, message, section)

    sources = _sources_with_portraits(anime, section)
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
            rich_message=_rich(text, urls),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich portrait view edit failed; falling back to standard text edit"
        )
        await message.edit_text(
            text=split_text(text, STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=keyboard,
        )


async def handle_people_callback(callback: CallbackQuery) -> bool:
    """Handle staff/voice callback namespaces before card handlers.

    Returns True only when this module consumed the callback. The portrait UI
    depends on explicit card services/state instead of a module-sized service
    locator, so its dependencies stay visible and testable.
    """
    raw = callback.data or ""
    parts = raw.split(":")

    if raw.startswith("av:"):
        if len(parts) != 4 or parts[2] not in PEOPLE_SECTIONS or not parts[3].isdigit():
            return False
        _, token, section, page_text = parts
        source_index: int | None = None
    elif raw.startswith("as:"):
        if (
            len(parts) != 5
            or parts[2] not in PEOPLE_SECTIONS
            or not parts[3].isdigit()
            or not parts[4].isdigit()
        ):
            return False
        _, token, section, source_index_text, page_text = parts
        source_index = int(source_index_text)
    else:
        return False

    anime = ANIME_SESSIONS.get(token)
    if anime is None:
        await callback.answer(
            "Карточка устарела. Выполни поиск ещё раз.",
            show_alert=True,
        )
        return True
    if callback.message is None:
        await callback.answer()
        return True

    await callback.answer()
    try:
        await _edit_people_view(
            callback.message,
            token,
            anime,
            section,
            source_index=source_index,
            page=int(page_text),
        )
    except ValueError:
        logging.debug("People callback source is no longer available", exc_info=True)
        try:
            await callback.message.edit_text(
                text="Источник больше недоступен. Вернись в карточку и открой раздел снова.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="← Назад",
                            callback_data=f"av:{token}:main:0",
                        )
                    ]]
                ),
            )
        except Exception:
            logging.exception("Could not render stale people callback fallback")
    return True
