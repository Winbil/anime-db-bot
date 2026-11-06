from __future__ import annotations

import logging
from collections.abc import Mapping

from aiogram.types import Message

from bots.telegram.card.ui.constants import STANDARD_MESSAGE_LIMIT
from bots.telegram.card.ui.keyboards import navigation_keyboard
from bots.telegram.card.views.rendering import rich
from core.models import AggregatedAnime
from localization import text
from mappings.resolver import MappingResolver

PAGE_LIMIT = STANDARD_MESSAGE_LIMIT - 200


def mapping_ids_pages(
    amdb_id: str,
    source_ids: Mapping[str, tuple[str, ...]],
    *,
    locale: str,
) -> list[str]:
    """Paginate all of an AMDB title's source-native IDs without dropping rows."""
    title = text("card", "all_ids_title", locale=locale)
    if not source_ids:
        return [title + "\n\n" + text("card", "all_ids_empty", locale=locale)]

    rows = [f"AMDB: {amdb_id.removeprefix('amdb:')}"]
    for provider, ids in sorted(source_ids.items()):
        if provider == "amdb":
            continue
        for external_id in ids:
            rows.append(f"{provider.upper()}: {external_id}")

    header = title + "\n\n"
    pages: list[str] = []
    current = header
    for line in rows:
        addition = line + "\n"
        if len(current) + len(addition) > PAGE_LIMIT and current != header:
            pages.append(current.rstrip())
            current = header
        if len(header) + len(addition) > PAGE_LIMIT:
            from bots.telegram.card.views.rendering import split_text

            pages.extend(split_text(line, PAGE_LIMIT, locale=locale))
            continue
        current += addition
    if current != header:
        pages.append(current.rstrip())
    return pages or [title + "\n\n" + text("card", "all_ids_empty", locale=locale)]


async def edit_mapping_ids_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    *,
    mapping_resolver: MappingResolver,
    page: int,
    locale: str,
) -> None:
    """Replace the current card with IDs from its verified AMDB anchor."""
    source_ids = (
        mapping_resolver.ids_for_anchor(anime.amdb_id) if anime.amdb_id else {}
    )
    pages = mapping_ids_pages(anime.amdb_id or "", source_ids, locale=locale)
    page = max(0, min(int(page), len(pages) - 1))
    keyboard = navigation_keyboard(
        token, anime, "all_ids", page, len(pages), locale=locale
    )
    try:
        await message.edit_text(
            rich_message=rich(pages[page]),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich AMDB ID view failed; using plain text")
        await message.edit_text(text=pages[page], reply_markup=keyboard)
