from __future__ import annotations

import asyncio
import html
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.constants import ALL_SOURCE_LABELS, STANDARD_MESSAGE_LIMIT
from bots.telegram.card.renderer import plain_text_to_rich_html, split_text
from bots.telegram.card.service import AGGREGATOR, SOURCES
from bots.telegram.card.state import ANIME_SESSIONS
from core.canonicalization import display_person_name, localize_role_token
from core.models import AggregatedAnime, PersonCredit
from core.people_loading import PeopleBatch
from localization import text
from services.user_settings import get_user_locale

PEOPLE_SECTIONS = {"staff", "voices"}


@dataclass(slots=True)
class _SourceLoadProgress:
    source: Any
    cursor: str | None = None
    complete: bool = False
    total_count: int | None = None
    task: asyncio.Task[bool] | None = None


@dataclass(slots=True)
class _PeopleLoadProgress:
    sources: dict[str, _SourceLoadProgress] = field(default_factory=dict)


_PEOPLE_LOADS: ExpiringSessionStore[_PeopleLoadProgress] = ExpiringSessionStore(
    max_entries=400
)


def _portrait_batch_size() -> int:
    raw = os.getenv("PEOPLE_PORTRAIT_BATCH_SIZE", "50").strip()
    try:
        return max(1, min(int(raw), 200))
    except ValueError:
        return 50


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


def _localized_roles(person: PersonCredit, locale: str) -> str:
    return ", ".join(
        localize_role_token(role, locale=locale)
        for role in person.roles
        if localize_role_token(role, locale=locale)
    ) or text("common", "role_not_specified", locale=locale)


def _person_line(person: PersonCredit, locale: str) -> str:
    name = display_person_name(person.name, person.aliases, locale=locale)
    return f"• {name} — {_localized_roles(person, locale)}"


def _page_text(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
    page: int,
    *,
    locale: str,
    total_hint: int | None = None,
) -> tuple[str, list[str], int, int, int]:
    without, with_portraits = _people_state(anime, section, source)
    actual_total = len(without) + len(with_portraits)
    total = max(actual_total, int(total_hint or 0))
    max_page = len(with_portraits)
    page = max(0, min(page, max_page))

    title_value = text("people", section, locale=locale)
    if source:
        title_value += f" — {source}"

    if page == 0:
        lines = [
            f"{title_value}:",
            "",
            text("people", "without_portrait", locale=locale),
        ]
        if without:
            lines.extend(_person_line(person, locale) for person in without)
        else:
            lines.append(text("people", "none", locale=locale))
        return "\n".join(lines), [], len(without), total, page

    person = with_portraits[page - 1]
    portrait_sources = _portrait_source_names(person, anime.sources)
    urls = _portrait_urls(
        person,
        source=source,
        source_order=anime.sources,
    )

    lines = [
        f"{title_value}:",
        "",
        display_person_name(person.name, person.aliases, locale=locale),
        text("people", "roles", locale=locale, roles=_localized_roles(person, locale)),
    ]
    if portrait_sources:
        lines.append(
            text(
                "people",
                "portraits",
                locale=locale,
                sources=", ".join(portrait_sources),
            )
        )

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


def _rich(text_value: str, urls: list[str]) -> InputRichMessage:
    return InputRichMessage(
        html=_portrait_html(urls) + plain_text_to_rich_html(text_value)
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


def _progress_key(token: str, section: str) -> str:
    return f"{token}:{section}"


def _build_progress(anime: AggregatedAnime, section: str) -> _PeopleLoadProgress:
    identity = anime.identity
    mapping = _section_mapping(anime, section)
    progress = _PeopleLoadProgress()

    for source in SOURCES:
        source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
        if source_key and not identity.has(source_key):
            continue

        batch_loader = getattr(source, f"load_{section}_batch", None)
        full_loader = getattr(source, f"load_{section}", None)
        if not callable(batch_loader) and not callable(full_loader):
            continue

        already_loaded = source.name in mapping
        progress.sources[source.name] = _SourceLoadProgress(
            source=source,
            complete=already_loaded,
            total_count=len(mapping.get(source.name, [])) if already_loaded else None,
        )
    return progress


def _source_names(
    anime: AggregatedAnime,
    section: str,
    progress: _PeopleLoadProgress | None,
) -> list[str]:
    if progress is not None and progress.sources:
        return list(progress.sources)
    return _sources_with_portraits(anime, section)


def _scope_progresses(
    progress: _PeopleLoadProgress,
    source: str | None,
) -> list[_SourceLoadProgress]:
    if source is None:
        return list(progress.sources.values())
    item = progress.sources.get(source)
    return [item] if item is not None else []


def _scope_has_more(
    progress: _PeopleLoadProgress,
    source: str | None,
) -> bool:
    return any(
        not item.complete or item.task is not None
        for item in _scope_progresses(progress, source)
    )


def _scope_total_hint(
    anime: AggregatedAnime,
    section: str,
    progress: _PeopleLoadProgress,
    source: str | None,
) -> int | None:
    actual = len(_people_for_scope(anime, section, source))
    if source is not None:
        item = progress.sources.get(source)
        if item is None or item.total_count is None:
            return actual or None
        return max(actual, item.total_count)

    hints = [
        item.total_count
        for item in progress.sources.values()
        if item.total_count is not None
    ]
    return max([actual, *hints]) if actual or hints else None


def _source_rows(
    token: str,
    anime: AggregatedAnime,
    section: str,
    selected_source_index: int | None,
    *,
    locale: str,
    source_names: list[str] | None = None,
) -> list[list[InlineKeyboardButton]]:
    sources = list(source_names or _sources_with_portraits(anime, section))
    if not sources:
        return []

    all_label = text("card", ALL_SOURCE_LABELS[section], locale=locale)
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
    *,
    locale: str,
    source_names: list[str] | None = None,
    has_more: bool = False,
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
            text=text("people", "shown", locale=locale, shown=shown, total=total),
            callback_data="noop",
        )
    )
    if page < max_page or has_more:
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
            locale=locale,
            source_names=source_names,
        )
    )

    rows.append([
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
            callback_data=f"av:{token}:main:0",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _merge_people_batch(
    anime: AggregatedAnime,
    section: str,
    source_name: str,
    batch: PeopleBatch,
) -> None:
    mapping = _section_mapping(anime, section)
    existing = list(mapping.get(source_name, []))
    AGGREGATOR.merge_people_source(
        anime,
        source_name=source_name,
        people=[*existing, *batch.people],
        section=section,
    )


async def _run_source_batch(
    anime: AggregatedAnime,
    section: str,
    item: _SourceLoadProgress,
) -> bool:
    source = item.source
    try:
        identity = anime.identity
        batch_loader = getattr(source, f"load_{section}_batch", None)
        if callable(batch_loader):
            batch = await batch_loader(
                identity.copy(),
                cursor=item.cursor,
                portrait_limit=_portrait_batch_size(),
            )
        else:
            full_loader = getattr(source, f"load_{section}", None)
            if not callable(full_loader):
                item.complete = True
                return False
            people = await full_loader(identity.copy())
            batch = PeopleBatch(
                people=people,
                complete=True,
                total_count=len(people),
            )

        _merge_people_batch(anime, section, source.name, batch)
        if batch.total_count is not None:
            item.total_count = max(item.total_count or 0, int(batch.total_count))
        item.cursor = batch.next_cursor
        item.complete = bool(batch.complete or batch.next_cursor is None)

        source_people = _section_mapping(anime, section).get(source.name, [])
        source_portraits = sum(
            1
            for person in source_people
            if _portrait_urls(person, source=source.name)
        )
        logging.info(
            "Progressive %s loaded from %s: batch_people=%d, total_people=%d, "
            "portraits=%d, complete=%s, cursor=%s",
            section,
            source.name,
            len(batch.people),
            len(source_people),
            source_portraits,
            item.complete,
            item.cursor,
        )
        return bool(batch.people)
    except asyncio.CancelledError:
        raise
    except Exception:
        item.complete = True
        logging.exception("Progressive %s load failed for %s", section, source.name)
        return False
    finally:
        item.task = None


def _start_source_batch(
    anime: AggregatedAnime,
    section: str,
    item: _SourceLoadProgress,
) -> asyncio.Task[bool] | None:
    if item.complete or item.task is not None:
        return item.task
    task = asyncio.create_task(_run_source_batch(anime, section, item))
    item.task = task
    return task


def _start_scope_batches(
    anime: AggregatedAnime,
    section: str,
    progress: _PeopleLoadProgress,
    source: str | None,
) -> list[asyncio.Task[bool]]:
    tasks: list[asyncio.Task[bool]] = []
    for item in _scope_progresses(progress, source):
        task = _start_source_batch(anime, section, item)
        if task is not None:
            tasks.append(task)
    return tasks


async def _await_one_scope_batch(
    anime: AggregatedAnime,
    section: str,
    progress: _PeopleLoadProgress,
    source: str | None,
) -> None:
    tasks = [
        item.task
        for item in _scope_progresses(progress, source)
        if item.task is not None
    ]
    if not tasks:
        tasks = _start_scope_batches(anime, section, progress, source)
    if not tasks:
        return

    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        try:
            await task
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Unexpected progressive people task failure")


async def _ensure_lazy_people(
    token: str,
    anime: AggregatedAnime,
    message: Message,
    section: str,
    *,
    locale: str,
    source: str | None = None,
    requested_page: int = 0,
) -> _PeopleLoadProgress:
    """Ensure enough people data exists for the requested portrait page.

    The first visit starts one batch for every capable source concurrently but
    returns as soon as any source provides usable data. Slower sources continue
    their first bounded batch in the background. Further batches are started only
    when pagination reaches the currently loaded portrait boundary.
    """
    key = _progress_key(token, section)
    progress = _PEOPLE_LOADS.get(key)
    created = progress is None
    if progress is None:
        progress = _build_progress(anime, section)
        _PEOPLE_LOADS[key] = progress

    if not progress.sources:
        return progress

    if created:
        if not _all_people(anime, section):
            loading_key = "loading_staff" if section == "staff" else "loading_voices"
            try:
                await message.edit_text(
                    text=text("people", loading_key, locale=locale),
                    reply_markup=None,
                )
            except Exception:
                logging.debug(
                    "Could not show progressive people loading state",
                    exc_info=True,
                )
        _start_scope_batches(anime, section, progress, None)

    def current_people() -> list[PersonCredit]:
        return _people_for_scope(anime, section, source)

    def current_portraits() -> int:
        return len(_people_state(anime, section, source)[1])

    # Do not block the first render on every source. One successful source is
    # enough to establish the people list/total while slower sources keep loading.
    while not current_people() and _scope_has_more(progress, source):
        await _await_one_scope_batch(anime, section, progress, source)

    requested_page = max(0, int(requested_page))
    while (
        requested_page > current_portraits()
        and _scope_has_more(progress, source)
    ):
        await _await_one_scope_batch(anime, section, progress, source)

    return progress


async def _edit_people_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int | None,
    page: int,
    *,
    locale: str,
) -> None:
    key = _progress_key(token, section)
    existing_progress = _PEOPLE_LOADS.get(key)
    existing_sources = _source_names(anime, section, existing_progress)

    source: str | None = None
    if source_index is not None:
        if source_index < 0 or source_index >= len(existing_sources):
            raise ValueError("Portrait source index is out of range")
        source = existing_sources[source_index]

    progress = await _ensure_lazy_people(
        token,
        anime,
        message,
        section,
        locale=locale,
        source=source,
        requested_page=int(page),
    )

    sources = _source_names(anime, section, progress)
    if source_index is not None:
        if source_index < 0 or source_index >= len(sources):
            raise ValueError("Portrait source index is out of range")
        source = sources[source_index]

    without, with_portraits = _people_state(anime, section, source)
    max_page = len(with_portraits)
    page = max(0, min(int(page), max_page))
    total_hint = _scope_total_hint(anime, section, progress, source)
    text_value, urls, shown, total, page = _page_text(
        anime,
        section,
        source,
        page,
        locale=locale,
        total_hint=total_hint,
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
        locale=locale,
        source_names=sources,
        has_more=_scope_has_more(progress, source),
    )

    try:
        await message.edit_text(
            rich_message=_rich(text_value, urls),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich portrait view edit failed; falling back to standard text edit"
        )
        await message.edit_text(
            text=split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)[0],
            reply_markup=keyboard,
        )


async def handle_people_callback(callback: CallbackQuery) -> bool:
    """Handle staff/voice callback namespaces before card handlers."""
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

    locale = get_user_locale(callback.from_user.id)
    session = ANIME_SESSIONS.get(token)
    if session is None:
        await callback.answer(text("card", "expired", locale=locale), show_alert=True)
        return True
    if session.owner_user_id != callback.from_user.id:
        await callback.answer(text("card", "not_owner", locale=locale), show_alert=True)
        return True
    if callback.message is None:
        await callback.answer()
        return True

    anime = session.anime
    await callback.answer()
    try:
        await _edit_people_view(
            callback.message,
            token,
            anime,
            section,
            source_index=source_index,
            page=int(page_text),
            locale=locale,
        )
    except ValueError:
        logging.debug("People callback source is no longer available", exc_info=True)
        try:
            await callback.message.edit_text(
                text=text("people", "source_unavailable", locale=locale),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text=text("common", "back", locale=locale),
                            callback_data=f"av:{token}:main:0",
                        )
                    ]]
                ),
            )
        except Exception:
            logging.exception("Could not render stale people callback fallback")
    return True
