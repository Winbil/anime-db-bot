from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bots.telegram.callbacks import KeyedPageCallback
from bots.telegram.card.runtime.service import aggregate_and_send
from bots.telegram.card.runtime.state import AnimeCardSession, TelegramCardState
from bots.telegram.card.views.renderer import edit_standard_text
from bots.telegram.card.views.titles import preferred_title_keys
from core.related_anime import AggregatedAnimeReference
from localization import text
from services.runtime.app_context import get_app_context

RELATED_PAGE_SIZE = 6
_SECTIONS = {"related", "recommendations"}


def _items(session: AnimeCardSession, section: str) -> list[AggregatedAnimeReference]:
    if section == "related":
        return session.related_items
    if section == "recommendations":
        return session.recommendation_items
    raise ValueError(f"Unsupported related anime section: {section}")


def _errors(session: AnimeCardSession, section: str) -> dict[str, str]:
    if section == "related":
        return session.related_errors
    if section == "recommendations":
        return session.recommendation_errors
    raise ValueError(f"Unsupported related anime section: {section}")


def _display_title(item: AggregatedAnimeReference, locale: str) -> str:
    for key in preferred_title_keys(locale):
        value = str(item.titles.get(key) or "").strip()
        if value:
            return value
    return item.candidate.title


def _truncate(value: str, limit: int = 52) -> str:
    value = " ".join(str(value or "").split()).strip()
    return value if len(value) <= limit else value[: max(1, limit - 1)].rstrip() + "…"


def _relation_label(item: AggregatedAnimeReference, locale: str) -> str | None:
    if not item.relations:
        return None
    labels = [
        text("relation_type", value, locale=locale, default=value.replace("_", " "))
        for value in item.relations[:2]
    ]
    return "/".join(labels)


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
        session.related_errors = result.errors
        session.related_loaded = True
        return
    if session.recommendations_loaded:
        return
    result = await context.related_anime_service.load_recommendations(
        session.anime.identity
    )
    session.recommendation_items = result.items
    session.recommendation_errors = result.errors
    session.recommendations_loaded = True


def related_keyboard(
    token: str,
    section: str,
    items: list[AggregatedAnimeReference],
    page: int,
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    page_count = max(1, (len(items) + RELATED_PAGE_SIZE - 1) // RELATED_PAGE_SIZE)
    page = max(0, min(int(page), page_count - 1))
    start = page * RELATED_PAGE_SIZE
    rows: list[list[InlineKeyboardButton]] = []
    for index, item in enumerate(items[start : start + RELATED_PAGE_SIZE], start):
        title = _display_title(item, locale)
        relation = _relation_label(item, locale) if section == "related" else None
        label = f"{relation} · {title}" if relation else title
        rows.append(
            [
                InlineKeyboardButton(
                    text=_truncate(label),
                    callback_data=KeyedPageCallback(
                        "ari", token, section, index
                    ).encode(),
                )
            ]
        )

    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️", callback_data=f"av:{token}:{section}:{page - 1}"
                )
            )
        nav.append(
            InlineKeyboardButton(text=f"{page + 1}/{page_count}", callback_data="noop")
        )
        if page + 1 < page_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️", callback_data=f"av:{token}:{section}:{page + 1}"
                )
            )
        rows.append(nav)

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
    locale: str,
) -> None:
    await ensure_related_loaded(session, section)
    items = _items(session, section)
    errors = _errors(session, section)
    page_count = max(1, (len(items) + RELATED_PAGE_SIZE - 1) // RELATED_PAGE_SIZE)
    page = max(0, min(int(page), page_count - 1))
    lines = [text("card", f"section_{section}", locale=locale)]
    if items:
        lines.append(text("card", "discovery_count", locale=locale, count=len(items)))
        sources: list[str] = []
        seen: set[str] = set()
        for item in items:
            for source in item.sources:
                key = source.casefold()
                if key not in seen:
                    seen.add(key)
                    sources.append(source)
        if sources:
            lines.append(
                text(
                    "card",
                    "discovery_sources",
                    locale=locale,
                    sources=", ".join(sources),
                )
            )
    else:
        lines.extend(["", text("common", "no_data", locale=locale)])
    if errors:
        lines.append(
            text("card", "unavailable", locale=locale, value=", ".join(errors))
        )
    await edit_standard_text(
        message,
        "\n".join(lines),
        reply_markup=related_keyboard(token, section, items, page, locale=locale),
        locale=locale,
    )


async def send_related_item(
    message: Message,
    session: AnimeCardSession,
    state: TelegramCardState,
    *,
    section: str,
    index: int,
    owner_user_id: int,
) -> None:
    await ensure_related_loaded(session, section)
    items = _items(session, section)
    if not 0 <= int(index) < len(items):
        raise IndexError(index)
    await aggregate_and_send(
        message,
        items[int(index)].candidate,
        owner_user_id,
        state,
    )
