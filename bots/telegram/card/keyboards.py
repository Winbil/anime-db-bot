from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bots.telegram.card.constants import ALL_SOURCE_LABELS, SOURCE_SELECTABLE_SECTIONS
from bots.telegram.card.selectors import (
    description_sources,
    ordered_mapping_items,
    source_section_sources,
)
from core.models import AggregatedAnime
from localization import text


def description_selection_rows(
    token: str,
    anime: AggregatedAnime,
) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(
            text=source,
            callback_data=f"ad:{token}:{index}:0",
        )
        for index, source in enumerate(description_sources(anime))
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def source_section_selection_rows(
    token: str,
    anime: AggregatedAnime,
    section: str,
    *,
    locale: str,
    selected_source_index: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    sources = source_section_sources(anime, section)
    if not sources:
        return []

    rows: list[list[InlineKeyboardButton]] = []
    all_label_key = ALL_SOURCE_LABELS.get(section)
    if all_label_key is not None:
        all_label = text("card", all_label_key, locale=locale)
        rows.append([
            InlineKeyboardButton(
                text=("✓ " + all_label) if selected_source_index is None else all_label,
                callback_data=f"av:{token}:{section}:0",
            )
        ])

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


def link_rows(anime: AggregatedAnime) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(text=source, url=str(url))
        for source, url in ordered_mapping_items(anime.urls, anime.sources)
        if str(url).strip()
    ]
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def navigation_keyboard(
    token: str,
    anime: AggregatedAnime,
    current_section: str,
    page: int,
    page_count: int,
    *,
    locale: str,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []

    if current_section == "description":
        rows.extend(description_selection_rows(token, anime))
    elif current_section == "links":
        rows.extend(link_rows(anime))
    elif current_section in SOURCE_SELECTABLE_SECTIONS:
        rows.extend(
            source_section_selection_rows(
                token,
                anime,
                current_section,
                locale=locale,
                selected_source_index=None,
            )
        )

    if current_section != "main":
        rows.append([
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
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


def description_keyboard(
    token: str,
    source_index: int,
    page: int,
    page_count: int,
    *,
    locale: str,
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
            text=text("common", "sources", locale=locale),
            callback_data=f"av:{token}:description:0",
        ),
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
            callback_data=f"av:{token}:main:0",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def source_section_keyboard(
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int,
    page: int,
    page_count: int,
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    rows = source_section_selection_rows(
        token,
        anime,
        section,
        locale=locale,
        selected_source_index=source_index,
    )

    rows.append([
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
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


def fallback_main_keyboard(token: str, *, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=text("card", "description_button", locale=locale),
                callback_data=f"av:{token}:description:0",
            ),
            InlineKeyboardButton(
                text=text("card", "section_titles", locale=locale),
                callback_data=f"av:{token}:titles:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text=text("card", "section_staff", locale=locale),
                callback_data=f"av:{token}:staff:0",
            ),
            InlineKeyboardButton(
                text=text("card", "section_voices", locale=locale),
                callback_data=f"av:{token}:voices:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text=text("card", "popularity_button", locale=locale),
                callback_data=f"av:{token}:popularity:0",
            ),
            InlineKeyboardButton(
                text=text("card", "links_button", locale=locale),
                callback_data=f"av:{token}:links:0",
            ),
        ],
    ])
