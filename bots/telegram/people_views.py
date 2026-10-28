from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage

from bots.telegram.callbacks import SectionSourceCallback, ViewCallback
from bots.telegram.card.constants import ALL_SOURCE_LABELS
from bots.telegram.card.renderer import plain_text_to_rich_html
from core.canonicalization import display_person_name, localize_role_token
from core.models import AggregatedAnime, PersonCredit
from localization import text

PEOPLE_SECTIONS = {"staff", "voices"}


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


def _portrait_source_names(person: PersonCredit, source_order: list[str]) -> list[str]:
    available = {
        source for source, urls in person.portraits.items() if _dedupe(list(urls or []))
    }
    ordered = [source for source in source_order if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _sources_with_portraits(anime: AggregatedAnime, section: str) -> list[str]:
    mapping = _section_mapping(anime, section)
    available = {
        source
        for source, people in mapping.items()
        if any(_portrait_urls(person, source=source) for person in people)
    }
    ordered = [source for source in anime.sources if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _people_for_scope(anime: AggregatedAnime, section: str, source: str | None) -> list[PersonCredit]:
    return _all_people(anime, section) if source is None else _section_mapping(anime, section).get(source, [])


def _people_state(
    anime: AggregatedAnime,
    section: str,
    source: str | None,
) -> tuple[list[PersonCredit], list[PersonCredit]]:
    without: list[PersonCredit] = []
    with_portraits: list[PersonCredit] = []
    for person in _people_for_scope(anime, section, source):
        urls = _portrait_urls(person, source=source, source_order=anime.sources)
        (with_portraits if urls else without).append(person)
    return without, with_portraits


def _first_people_page(without: list[PersonCredit], with_portraits: list[PersonCredit]) -> int:
    return 0 if without or not with_portraits else 1


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
        lines = [f"{title_value}:", "", text("people", "without_portrait", locale=locale)]
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
        lines.append(text("people", "portraits", locale=locale, sources=", ".join(portrait_sources)))
    return "\n".join(lines), urls, len(without) + page, total, page


def _portrait_html(urls: list[str]) -> str:
    urls = _dedupe(urls)[:20]
    if not urls:
        return ""
    images = "".join(f'<img src="{html.escape(url, quote=True)}"/>' for url in urls)
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def _rich(text_value: str, urls: list[str]) -> InputRichMessage:
    return InputRichMessage(html=_portrait_html(urls) + plain_text_to_rich_html(text_value))


def _page_callback(token: str, section: str, source_index: int | None, page: int) -> str:
    if source_index is None:
        return ViewCallback(token, section, page).encode()
    return SectionSourceCallback(token, section, source_index, page).encode()


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
    rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(
        text=("✓ " + all_label) if selected_source_index is None else all_label,
        callback_data=ViewCallback(token, section, 0).encode(),
    )]]
    buttons = [
        InlineKeyboardButton(
            text=("✓ " + source) if selected_source_index == index else source,
            callback_data=SectionSourceCallback(token, section, index, 0).encode(),
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
    first_page: int = 0,
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > first_page:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=_page_callback(token, section, source_index, page - 1)))
    nav.append(InlineKeyboardButton(
        text=text("people", "shown", locale=locale, shown=shown, total=total),
        callback_data="noop",
    ))
    if page < max_page or has_more:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=_page_callback(token, section, source_index, page + 1)))
    rows: list[list[InlineKeyboardButton]] = [nav]
    rows.extend(_source_rows(token, anime, section, source_index, locale=locale, source_names=source_names))
    rows.append([InlineKeyboardButton(
        text=text("common", "back", locale=locale),
        callback_data=ViewCallback(token, "main", 0).encode(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
