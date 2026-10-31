from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bots.telegram.callbacks import KeyedPageCallback, SectionSourceCallback
from bots.telegram.pagination import card_picker_callback
from bots.telegram.card.ui.constants import (
    ALL_SOURCE_LABELS,
    SOURCE_SELECTABLE_SECTIONS,
)
from bots.telegram.card.ui.selectors import (
    description_source_options,
    ordered_mapping_items,
    source_section_options,
)
from core.models import AggregatedAnime
from localization import text


def description_selection_rows(
    token: str,
    anime: AggregatedAnime,
) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(
            text=source_name,
            callback_data=KeyedPageCallback("ad", token, source_key, 0).encode(),
        )
        for source_key, source_name in description_source_options(anime)
    ]
    return [buttons[index : index + 2] for index in range(0, len(buttons), 2)]


def source_section_selection_rows(
    token: str,
    anime: AggregatedAnime,
    section: str,
    *,
    locale: str,
    selected_source_key: str | None = None,
) -> list[list[InlineKeyboardButton]]:
    sources = source_section_options(anime, section)
    if not sources:
        return []

    rows: list[list[InlineKeyboardButton]] = []
    all_label_key = ALL_SOURCE_LABELS.get(section)
    if all_label_key is not None:
        all_label = text("card", all_label_key, locale=locale)
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✓ " + all_label)
                    if selected_source_key is None
                    else all_label,
                    callback_data=f"av:{token}:{section}:0",
                )
            ]
        )

    source_buttons = [
        InlineKeyboardButton(
            text=("✓ " + source_name)
            if selected_source_key == source_key
            else source_name,
            callback_data=SectionSourceCallback(token, section, source_key, 0).encode(),
        )
        for source_key, source_name in sources
    ]
    rows.extend(
        source_buttons[index : index + 2] for index in range(0, len(source_buttons), 2)
    )
    return rows


def link_rows(anime: AggregatedAnime) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(text=source, url=str(url))
        for source, url in ordered_mapping_items(anime.urls, anime.sources)
        if str(url).strip()
    ]
    return [buttons[index : index + 2] for index in range(0, len(buttons), 2)]


def navigation_keyboard(
    token: str,
    anime: AggregatedAnime,
    current_section: str,
    page: int,
    page_count: int,
    *,
    locale: str,
    pagination_first: bool = False,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []

    nav: list[InlineKeyboardButton] = []
    if page_count > 1 and current_section not in {"description", "links"}:
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"av:{token}:{current_section}:{page - 1}",
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{page_count}",
                callback_data=card_picker_callback(
                    token, f"av~{current_section}", page, page_count
                ),
            )
        )
        if page + 1 < page_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"av:{token}:{current_section}:{page + 1}",
                )
            )
        if pagination_first:
            rows.append(nav)

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
                selected_source_key=None,
            )
        )

    if current_section != "main":
        rows.append(
            [
                InlineKeyboardButton(
                    text=text("common", "back", locale=locale),
                    callback_data=f"av:{token}:main:0",
                )
            ]
        )

    if nav and not pagination_first:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def description_keyboard(
    token: str,
    source_key: str,
    page: int,
    page_count: int,
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=KeyedPageCallback(
                        "ad", token, source_key, page - 1
                    ).encode(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{page_count}",
                callback_data=card_picker_callback(
                    token, f"ad~{source_key}", page, page_count
                ),
            )
        )
        if page + 1 < page_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=KeyedPageCallback(
                        "ad", token, source_key, page + 1
                    ).encode(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "sources", locale=locale),
                callback_data=f"av:{token}:description:0",
            ),
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=f"av:{token}:main:0",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def source_section_keyboard(
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_key: str,
    page: int,
    page_count: int,
    *,
    locale: str,
    pagination_first: bool = False,
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page_count > 1:
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=SectionSourceCallback(
                        token, section, source_key, page - 1
                    ).encode(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{page_count}",
                callback_data=card_picker_callback(
                    token, f"as~{section}~{source_key}", page, page_count
                ),
            )
        )
        if page + 1 < page_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=SectionSourceCallback(
                        token, section, source_key, page + 1
                    ).encode(),
                )
            )

    rows: list[list[InlineKeyboardButton]] = []
    if nav and pagination_first:
        rows.append(nav)
    rows.extend(
        source_section_selection_rows(
            token,
            anime,
            section,
            locale=locale,
            selected_source_key=source_key,
        )
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=f"av:{token}:main:0",
            )
        ]
    )

    if nav and not pagination_first:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def fallback_main_keyboard(token: str, *, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                    text=text("card", "characters_button", locale=locale),
                    callback_data=f"av:{token}:characters:0",
                ),
                InlineKeyboardButton(
                    text=text("card", "screenshots_button", locale=locale),
                    callback_data=f"av:{token}:screenshots:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=text("card", "popularity_button", locale=locale),
                    callback_data=f"av:{token}:popularity:0",
                ),
                InlineKeyboardButton(
                    text=text("card", "episodes_button", locale=locale),
                    callback_data=f"av:{token}:episodes:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=text("card", "release_schedule_button", locale=locale),
                    callback_data=f"av:{token}:release_schedule:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=text("card", "trailers_button", locale=locale),
                    callback_data=f"av:{token}:trailers:0",
                ),
                InlineKeyboardButton(
                    text=text("card", "links_button", locale=locale),
                    callback_data=f"av:{token}:links:0",
                ),
            ],
        ]
    )
