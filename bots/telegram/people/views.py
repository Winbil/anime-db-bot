from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage

from bots.telegram.callbacks import SectionSourceCallback, ViewCallback
from bots.telegram.card.ui.constants import ALL_SOURCE_LABELS
from bots.telegram.card.views.renderer import plain_text_to_rich_html
from bots.telegram.card.ui.selectors import source_options
from core.canonicalization import display_person_name, localize_role_token
from core.models import AggregatedAnime, PersonCredit
from core.people import (
    PEOPLE_SECTIONS,
    all_people as _all_people,
    dedupe_strings as _dedupe,
    first_people_page as _first_people_page,
    people_for_scope as _people_for_scope,
    people_state as _people_state,
    portrait_source_names as _portrait_source_names,
    portrait_urls as _portrait_urls,
    section_mapping as _section_mapping,
    sources_with_portraits as _sources_with_portraits,
)
from localization import text


def _localized_roles(person: PersonCredit, locale: str) -> str:
    roles = [
        localize_role_token(role, locale=locale)
        for role in person.roles
        if localize_role_token(role, locale=locale)
    ]
    return ", ".join(roles) or text("common", "role_not_specified", locale=locale)


def _person_line(person: PersonCredit, locale: str) -> str:
    return f"• {display_person_name(person.name, person.aliases, locale=locale)} — {_localized_roles(person, locale)}"


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
    first_page = _first_people_page(without, with_portraits)
    page = max(first_page, min(int(page), max_page))
    title_value = text("people", section, locale=locale)
    if source:
        title_value += f" — {source}"
    if page == 0:
        lines = [
            f"{title_value}:",
            "",
            text("people", "without_portrait", locale=locale),
        ]
        lines.extend(_person_line(person, locale) for person in without)
        if not without:
            lines.append(text("people", "none", locale=locale))
        return "\n".join(lines), [], len(without), total, page

    person = with_portraits[page - 1]
    portrait_sources = _portrait_source_names(person, anime.sources)
    urls = _portrait_urls(person, source=source, source_order=anime.sources)
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
    return "\n".join(lines), urls, len(without) + page, total, page


def _portrait_html(urls: list[str]) -> str:
    urls = _dedupe(urls)[:20]
    if not urls:
        return ""
    images = "".join(f'<img src="{html.escape(url, quote=True)}"/>' for url in urls)
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def _rich(text_value: str, urls: list[str]) -> InputRichMessage:
    return InputRichMessage(
        html=_portrait_html(urls) + plain_text_to_rich_html(text_value)
    )


def _page_callback(token: str, section: str, source_key: str | None, page: int) -> str:
    if source_key is None:
        return ViewCallback(token, section, page).encode()
    return SectionSourceCallback(token, section, source_key, page).encode()


def _source_rows(
    token: str,
    anime: AggregatedAnime,
    section: str,
    selected_source_key: str | None,
    *,
    locale: str,
    source_names: list[str] | None = None,
) -> list[list[InlineKeyboardButton]]:
    names = list(source_names or _sources_with_portraits(anime, section))
    sources = source_options(names)
    if not sources:
        return []
    all_label = text("card", ALL_SOURCE_LABELS[section], locale=locale)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=("✓ " + all_label) if selected_source_key is None else all_label,
                callback_data=ViewCallback(token, section, 0).encode(),
            )
        ]
    ]
    buttons = [
        InlineKeyboardButton(
            text=("✓ " + source_name)
            if selected_source_key == source_key
            else source_name,
            callback_data=SectionSourceCallback(token, section, source_key, 0).encode(),
        )
        for source_key, source_name in sources
    ]
    rows.extend(buttons[index : index + 2] for index in range(0, len(buttons), 2))
    return rows


def _keyboard(
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_key: str | None,
    page: int,
    shown: int,
    total: int,
    max_page: int,
    *,
    locale: str,
    source_names: list[str] | None = None,
    has_more: bool = False,
    first_page: int = 0,
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > first_page:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=_page_callback(token, section, source_key, page - 1),
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=text(
                "people",
                "shown",
                locale=locale,
                shown=shown,
                total=total,
            ),
            callback_data="noop",
        )
    )
    if page < max_page or has_more:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=_page_callback(token, section, source_key, page + 1),
            )
        )
    rows: list[list[InlineKeyboardButton]] = [nav]
    rows.extend(
        _source_rows(
            token,
            anime,
            section,
            source_key,
            locale=locale,
            source_names=source_names,
        )
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=ViewCallback(token, "main", 0).encode(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
