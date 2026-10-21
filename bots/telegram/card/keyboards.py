from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bots.telegram.card.constants import ALL_SOURCE_LABELS, SOURCE_SELECTABLE_SECTIONS
from bots.telegram.card.selectors import (
    description_sources,
    ordered_mapping_items,
    source_section_sources,
)
from core.models import AggregatedAnime


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
    selected_source_index: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    sources = source_section_sources(anime, section)
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


def description_keyboard(
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


def source_section_keyboard(
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int,
    page: int,
    page_count: int,
) -> InlineKeyboardMarkup:
    rows = source_section_selection_rows(
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


def fallback_main_keyboard(token: str) -> InlineKeyboardMarkup:
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
