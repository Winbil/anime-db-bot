from __future__ import annotations

import html
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bots.telegram.card.renderer import edit_standard_text, plain_text_to_rich_html
from bots.telegram.card.service import CHARACTER_SERVICE
from bots.telegram.card.state import AnimeCardSession
from core.canonicalization import display_person_name, person_identity_keys
from core.models import CharacterRecord
from localization import text


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


def _role_priority(role: str | None) -> int:
    return {"main": 3, "supporting": 2, "background": 1}.get((role or "").casefold(), 0)


def _merge_characters(groups: list[list[CharacterRecord]]) -> list[CharacterRecord]:
    merged: list[CharacterRecord] = []
    name_keys_by_index: list[set[str]] = []
    for group in groups:
        for character in group:
            names = _dedupe([character.name, *character.aliases])
            name_keys = person_identity_keys(names)
            identity = character.identity

            match_index = next(
                (
                    index
                    for index, existing in enumerate(merged)
                    if existing.identity.matches(identity)
                ),
                None,
            )
            matched_by_id = match_index is not None
            if match_index is None:
                match_index = next(
                    (
                        index
                        for index, existing in enumerate(merged)
                        if name_keys_by_index[index] & name_keys
                        and not existing.identity.conflicts_with(identity)
                    ),
                    None,
                )

            if match_index is None:
                merged.append(CharacterRecord(
                    name=character.name,
                    role=character.role,
                    aliases=list(character.aliases),
                    external_ids=dict(character.external_ids),
                    portraits={source: list(urls) for source, urls in character.portraits.items()},
                ))
                name_keys_by_index.append(name_keys)
                continue

            existing = merged[match_index]
            all_names = _dedupe([
                existing.name,
                *existing.aliases,
                character.name,
                *character.aliases,
            ])
            existing.aliases = [
                value
                for value in all_names
                if value.casefold() != existing.name.casefold()
            ]
            name_keys_by_index[match_index].update(name_keys)
            if _role_priority(character.role) > _role_priority(existing.role):
                existing.role = character.role
            if matched_by_id:
                merged_identity = existing.identity
                merged_identity.merge_missing(identity)
                existing.external_ids = dict(merged_identity.external_ids)
            elif not existing.external_ids and character.external_ids:
                # A name-only presentation merge may carry one source-local ID,
                # but it must not infer a new cross-provider mapping.
                existing.external_ids = dict(character.external_ids)
            for source_name, urls in character.portraits.items():
                existing.portraits[source_name] = _dedupe([
                    *existing.portraits.get(source_name, []),
                    *urls,
                ])
    return merged


def _source_names(session: AnimeCardSession) -> list[str]:
    available = set(session.anime.characters_by_source)
    ordered = [source for source in session.anime.sources if source in available]
    ordered.extend(source for source in session.anime.characters_by_source if source not in ordered)
    return ordered


def _characters(session: AnimeCardSession, source: str | None) -> list[CharacterRecord]:
    if source is not None:
        return session.anime.characters_by_source.get(source, [])
    groups = [session.anime.characters_by_source[source] for source in _source_names(session)]
    return _merge_characters(groups)


def _portrait_urls(character: CharacterRecord, source: str | None, source_order: list[str]) -> list[str]:
    if source is not None:
        return _dedupe(character.portraits.get(source, []))
    values: list[str] = []
    for source_name in source_order:
        values.extend(character.portraits.get(source_name, []))
    for source_name, urls in character.portraits.items():
        if source_name not in source_order:
            values.extend(urls)
    return _dedupe(values)


def _portrait_sources(character: CharacterRecord, source_order: list[str]) -> list[str]:
    available = {source for source, urls in character.portraits.items() if _dedupe(urls)}
    ordered = [source for source in source_order if source in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _role_label(role: str | None, locale: str) -> str:
    if not role:
        return text("common", "role_not_specified", locale=locale)
    return text("character_role", role, locale=locale, default=role)


def _character_line(character: CharacterRecord, locale: str) -> str:
    name = display_person_name(character.name, character.aliases, locale=locale)
    return f"• {name} — {_role_label(character.role, locale)}"


def _character_state(
    session: AnimeCardSession,
    source: str | None,
) -> tuple[list[CharacterRecord], list[CharacterRecord], list[CharacterRecord]]:
    source_order = _source_names(session)
    values = _characters(session, source)
    without: list[CharacterRecord] = []
    with_portraits: list[CharacterRecord] = []
    for character in values:
        if _portrait_urls(character, source, source_order):
            with_portraits.append(character)
        else:
            without.append(character)
    return values, without, with_portraits


def _first_character_page(
    without: list[CharacterRecord],
    with_portraits: list[CharacterRecord],
) -> int:
    if without or not with_portraits:
        return 0
    return 1


def _page_text(
    session: AnimeCardSession,
    source: str | None,
    page: int,
    *,
    locale: str,
) -> tuple[str, list[str], int, int, int]:
    source_order = _source_names(session)
    values, without, with_portraits = _character_state(session, source)

    total = len(values)
    max_page = len(with_portraits)
    first_page = _first_character_page(without, with_portraits)
    page = max(first_page, min(int(page), max_page))
    title = text("characters", "title", locale=locale)
    if source:
        title += f" — {source}"

    if page == 0:
        lines = [title + ":", "", text("characters", "without_portrait", locale=locale)]
        if without:
            lines.extend(_character_line(character, locale) for character in without)
        else:
            lines.append(text("characters", "none", locale=locale))
        return "\n".join(lines), [], len(without), total, page

    character = with_portraits[page - 1]
    urls = _portrait_urls(character, source, source_order)
    portrait_sources = _portrait_sources(character, source_order)
    lines = [
        title + ":",
        "",
        display_person_name(character.name, character.aliases, locale=locale),
        text("characters", "role", locale=locale, role=_role_label(character.role, locale)),
    ]
    if portrait_sources:
        lines.append(text("characters", "portraits", locale=locale, sources=", ".join(portrait_sources)))
    return "\n".join(lines), urls, len(without) + page, total, page


def _rich(text_value: str, urls: list[str]) -> InputRichMessage:
    urls = _dedupe(urls)[:20]
    images = "".join(f'<img src="{html.escape(url, quote=True)}"/>' for url in urls)
    media = images if len(urls) <= 1 else f"<tg-slideshow>{images}</tg-slideshow>"
    return InputRichMessage(html=media + plain_text_to_rich_html(text_value))


def _callback(token: str, source_index: int | None, page: int) -> str:
    if source_index is None:
        return f"av:{token}:characters:{page}"
    return f"ac:{token}:{source_index}:{page}"


def _keyboard(
    token: str,
    sources: list[str],
    source_index: int | None,
    page: int,
    shown: int,
    total: int,
    max_page: int,
    *,
    locale: str,
    first_page: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > first_page:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=_callback(token, source_index, page - 1)))
    nav.append(InlineKeyboardButton(
        text=text("characters", "shown", locale=locale, shown=shown, total=total),
        callback_data="noop",
    ))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=_callback(token, source_index, page + 1)))
    rows.append(nav)

    rows.append([InlineKeyboardButton(
        text=("✓ " if source_index is None else "") + text("characters", "all", locale=locale),
        callback_data=f"av:{token}:characters:0",
    )])
    buttons = [
        InlineKeyboardButton(
            text=("✓ " + source) if source_index == index else source,
            callback_data=f"ac:{token}:{index}:0",
        )
        for index, source in enumerate(sources)
    ]
    rows.extend(buttons[index:index + 2] for index in range(0, len(buttons), 2))
    rows.append([InlineKeyboardButton(
        text=text("common", "back", locale=locale),
        callback_data=f"av:{token}:main:0",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ensure_loaded(message: Message, session: AnimeCardSession, *, locale: str) -> None:
    if session.characters_loaded:
        return
    try:
        await message.edit_text(text=text("characters", "loading", locale=locale), reply_markup=None)
    except Exception:
        logging.debug("Could not show character loading state", exc_info=True)

    result = await CHARACTER_SERVICE.load(session.anime.identity)
    session.anime.characters_by_source = result.by_source
    session.anime.characters = _merge_characters([
        result.by_source[source]
        for source in session.anime.sources
        if source in result.by_source
    ] + [
        values for source, values in result.by_source.items() if source not in session.anime.sources
    ])
    session.character_errors = result.errors
    session.characters_loaded = True


async def edit_characters_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    source_index: int | None,
    page: int,
    locale: str,
) -> None:
    try:
        await _ensure_loaded(message, session, locale=locale)
    except Exception:
        logging.exception("Could not load characters")
        session.characters_loaded = True
        session.character_errors = {"characters": "load failed"}

    sources = _source_names(session)
    source: str | None = None
    if source_index is not None:
        if source_index < 0 or source_index >= len(sources):
            raise ValueError("Character source index is out of range")
        source = sources[source_index]

    values = _characters(session, source)
    if not values:
        content = text("characters", "load_failed", locale=locale) if session.character_errors else text("characters", "empty", locale=locale)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=text("common", "back", locale=locale), callback_data=f"av:{token}:main:0")
        ]])
    else:
        _, without, with_portraits = _character_state(session, source)
        max_page = len(with_portraits)
        first_page = _first_character_page(without, with_portraits)
        content, urls, shown, total, page = _page_text(session, source, page, locale=locale)
        keyboard = _keyboard(
            token,
            sources,
            source_index,
            page,
            shown,
            total,
            max_page,
            locale=locale,
            first_page=first_page,
        )
        try:
            await message.edit_text(rich_message=_rich(content, urls), reply_markup=keyboard)
            return
        except Exception:
            logging.exception("Rich character view edit failed; falling back to text")

    await edit_standard_text(
        message,
        content,
        reply_markup=keyboard,
        locale=locale,
    )
