from __future__ import annotations

import html
import logging

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from bots.telegram.callbacks import KeyedPageCallback
from bots.telegram.pagination import card_picker_callback
from bots.telegram.card.runtime.service import aggregate_and_send
from bots.telegram.card.runtime.state import AnimeCardSession, TelegramCardState
from bots.telegram.card.views.renderer import edit_standard_text
from bots.telegram.card.views.rendering import _table_html, image_gallery_html
from bots.telegram.card.views.titles import preferred_title_keys
from core.related_anime import AggregatedAnimeReference
from localization import text
from services.runtime.app_context import get_app_context

_SECTIONS = {"related", "recommendations"}
_ALL_SOURCE_KEY = "all"
_DISPLAY_ID_ORDER = ("mal", "anilist", "shikimori", "kitsu", "anidb", "anisearch")


def _section_data(
    session: AnimeCardSession,
    section: str,
) -> tuple[
    list[AggregatedAnimeReference],
    dict[str, list[AggregatedAnimeReference]],
    dict[str, str],
    dict[str, str],
]:
    if section == "related":
        return (
            session.related_items,
            session.related_by_source,
            session.related_source_names,
            session.related_errors,
        )
    if section == "recommendations":
        return (
            session.recommendation_items,
            session.recommendation_by_source,
            session.recommendation_source_names,
            session.recommendation_errors,
        )
    raise ValueError(f"Unsupported related anime section: {section}")


def _items(
    session: AnimeCardSession,
    section: str,
    source_key: str,
) -> list[AggregatedAnimeReference]:
    aggregate, by_source, _, _ = _section_data(session, section)
    if source_key == _ALL_SOURCE_KEY:
        return aggregate
    return by_source.get(source_key, [])


def _display_title(item: AggregatedAnimeReference, locale: str) -> str:
    for key in preferred_title_keys(locale):
        value = str(item.titles.get(key) or "").strip()
        if value:
            return value
    candidate = item.candidate.title.strip()
    if candidate and candidate != "Unknown anime":
        return candidate
    for key in _DISPLAY_ID_ORDER:
        value = str(item.external_ids.get(key) or "").strip()
        if value:
            return f"{key.upper()} #{value}"
    return "Unknown anime"


def _relation_label(item: AggregatedAnimeReference, locale: str) -> str | None:
    if not item.relations:
        return None
    labels = [
        text("relation_type", value, locale=locale, default=value.replace("_", " "))
        for value in item.relations[:3]
    ]
    return ", ".join(labels)


def _display_ids(item: AggregatedAnimeReference) -> str:
    values = [
        f"{key.upper()}: {item.external_ids[key]}"
        for key in _DISPLAY_ID_ORDER
        if item.external_ids.get(key)
    ]
    return " | ".join(values)


def _detail_lines(
    item: AggregatedAnimeReference,
    section: str,
    *,
    locale: str,
) -> list[str]:
    lines: list[str] = []
    if section == "related":
        relation = _relation_label(item, locale)
        if relation:
            lines.append(
                text("card", "discovery_relation", locale=locale, value=relation)
            )
    if item.sources:
        lines.append(
            text(
                "card",
                "databases",
                locale=locale,
                value=", ".join(item.sources),
            )
        )
    ids = _display_ids(item)
    if ids:
        lines.append(text("card", "ids", locale=locale, value=ids))
    return lines


def _detail_text(
    item: AggregatedAnimeReference,
    section: str,
    *,
    locale: str,
) -> str:
    lines = [
        text("card", f"section_{section}", locale=locale),
        "",
        _display_title(item, locale),
    ]
    lines.extend(_detail_lines(item, section, locale=locale))
    return "\n".join(lines)


def _detail_rich(
    item: AggregatedAnimeReference,
    section: str,
    *,
    locale: str,
) -> InputRichMessage:
    title = html.escape(_display_title(item, locale))
    table = _table_html(
        text("card", f"section_{section}", locale=locale),
        _detail_lines(item, section, locale=locale),
    )
    return InputRichMessage(
        html=image_gallery_html(item.posters, limit=1) + f"<h2>{title}</h2>" + table
    )


def _route_key(section: str, source_key: str) -> str:
    return f"{section}~{source_key}"


def parse_related_route(value: str) -> tuple[str, str] | None:
    section, separator, source_key = str(value or "").partition("~")
    if not separator:
        # Backward compatibility with callbacks from the first implementation.
        return (section, _ALL_SOURCE_KEY) if section in _SECTIONS else None
    if section not in _SECTIONS or not source_key:
        return None
    return section, source_key


async def ensure_related_loaded(session: AnimeCardSession, section: str) -> None:
    if section not in _SECTIONS:
        raise ValueError(f"Unsupported related anime section: {section}")
    context = get_app_context()
    if section == "related":
        if session.related_loaded:
            return
        result = await context.related_anime_service.load_relations(
            session.anime.identity
        )
        session.related_items = result.items
        session.related_by_source = result.by_source
        session.related_source_names = result.source_names
        session.related_errors = result.errors
        session.related_loaded = True
        return
    if session.recommendations_loaded:
        return
    result = await context.related_anime_service.load_recommendations(
        session.anime.identity
    )
    session.recommendation_items = result.items
    session.recommendation_by_source = result.by_source
    session.recommendation_source_names = result.source_names
    session.recommendation_errors = result.errors
    session.recommendations_loaded = True


def related_keyboard(
    token: str,
    section: str,
    items: list[AggregatedAnimeReference],
    page: int,
    *,
    source_key: str,
    source_names: dict[str, str],
    locale: str,
) -> InlineKeyboardMarkup:
    page_count = max(1, len(items))
    page = max(0, min(int(page), page_count - 1))
    rows: list[list[InlineKeyboardButton]] = []

    if items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=text("card", "discovery_open_card", locale=locale),
                    callback_data=KeyedPageCallback(
                        "ari", token, _route_key(section, source_key), page
                    ).encode(),
                )
            ]
        )

    if len(items) > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=KeyedPageCallback(
                        "ar", token, _route_key(section, source_key), page - 1
                    ).encode(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{len(items)}",
                callback_data=card_picker_callback(
                    token,
                    f"ar~{section}~{source_key}",
                    page,
                    len(items),
                ),
            )
        )
        if page + 1 < len(items):
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=KeyedPageCallback(
                        "ar", token, _route_key(section, source_key), page + 1
                    ).encode(),
                )
            )
        rows.append(nav)

    all_label = text("card", "discovery_all_sources", locale=locale)
    rows.append(
        [
            InlineKeyboardButton(
                text=(f"✓ {all_label}" if source_key == _ALL_SOURCE_KEY else all_label),
                callback_data=KeyedPageCallback(
                    "ar", token, _route_key(section, _ALL_SOURCE_KEY), 0
                ).encode(),
            )
        ]
    )
    source_buttons = [
        InlineKeyboardButton(
            text=(f"✓ {name}" if key == source_key else name),
            callback_data=KeyedPageCallback(
                "ar", token, _route_key(section, key), 0
            ).encode(),
        )
        for key, name in source_names.items()
    ]
    rows.extend(
        source_buttons[index : index + 2] for index in range(0, len(source_buttons), 2)
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=f"av:{token}:main:0",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def edit_related_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    section: str,
    page: int,
    source_key: str = _ALL_SOURCE_KEY,
    locale: str,
) -> None:
    await ensure_related_loaded(session, section)
    _, by_source, source_names, errors = _section_data(session, section)
    if source_key != _ALL_SOURCE_KEY and source_key not in by_source:
        source_key = _ALL_SOURCE_KEY
    items = _items(session, section, source_key)
    page_count = max(1, len(items))
    page = max(0, min(int(page), page_count - 1))
    keyboard = related_keyboard(
        token,
        section,
        items,
        page,
        source_key=source_key,
        source_names=source_names,
        locale=locale,
    )

    if not items:
        lines = [
            text("card", f"section_{section}", locale=locale),
            "",
            text("common", "no_data", locale=locale),
        ]
        if errors and source_key == _ALL_SOURCE_KEY:
            lines.append(
                text("card", "unavailable", locale=locale, value=", ".join(errors))
            )
        await edit_standard_text(
            message,
            "\n".join(lines),
            reply_markup=keyboard,
            locale=locale,
        )
        return

    item = items[page]
    try:
        await message.edit_text(
            rich_message=_detail_rich(item, section, locale=locale),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Rich related-anime edit failed; falling back to standard text edit"
        )
        await edit_standard_text(
            message,
            _detail_text(item, section, locale=locale),
            reply_markup=keyboard,
            locale=locale,
        )


async def send_related_item(
    message: Message,
    session: AnimeCardSession,
    state: TelegramCardState,
    *,
    section: str,
    source_key: str,
    index: int,
    owner_user_id: int,
) -> None:
    await ensure_related_loaded(session, section)
    items = _items(session, section, source_key)
    if not 0 <= int(index) < len(items):
        raise IndexError(index)
    await aggregate_and_send(
        message,
        items[int(index)].candidate,
        owner_user_id,
        state,
    )
