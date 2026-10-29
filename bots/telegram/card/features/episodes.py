from __future__ import annotations

import logging

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from bots.telegram.callbacks import (
    EpisodeDetailCallback,
    KeyedPageCallback,
    resolve_key_or_legacy_index,
)
from bots.telegram.card.views.renderer import (
    edit_standard_text,
    plain_text_to_rich_html,
)
from bots.telegram.card.runtime.state import AnimeCardSession
from core.models import EpisodeRecord
from localization import text
from services.runtime.app_context import get_app_context
from services.media.episodes import EpisodeService

EPISODES_PER_VIEW = 10
UPSTREAM_PAGE_SIZE = 100


def _view_slice(view_page: int) -> tuple[int, int]:
    view_page = max(0, int(view_page))
    views_per_upstream_page = max(1, UPSTREAM_PAGE_SIZE // EPISODES_PER_VIEW)
    upstream_page = view_page // views_per_upstream_page + 1
    offset = (view_page % views_per_upstream_page) * EPISODES_PER_VIEW
    return upstream_page, offset


def _episode_title(episode: EpisodeRecord, locale: str) -> str:
    order = (
        ("english", "romaji", "japanese")
        if locale == "en"
        else (
            "romaji",
            "english",
            "japanese",
        )
    )
    for key in order:
        value = (episode.titles.get(key) or "").strip()
        if value:
            return value
    return text("card", "episode_untitled", locale=locale)


def _episode_summary_lines(episode: EpisodeRecord, *, locale: str) -> list[str]:
    title = _episode_title(episode, locale)
    lines = [f"{episode.number}. {title}"]
    if episode.aired_at:
        lines.append(
            text(
                "card",
                "episode_date",
                locale=locale,
                value=episode.aired_at.isoformat(),
            )
        )
    if episode.score is not None:
        lines.append(
            text(
                "card",
                "episode_score",
                locale=locale,
                value=f"{episode.score:g}",
            )
        )
    flags: list[str] = []
    if episode.filler:
        flags.append(text("card", "episode_filler", locale=locale))
    if episode.recap:
        flags.append(text("card", "episode_recap", locale=locale))
    if flags:
        lines.append(", ".join(flags))
    return lines


def _episodes_text(
    items: list[EpisodeRecord],
    *,
    locale: str,
    source_name: str,
) -> str:
    lines = [text("card", "episodes_title", locale=locale, source=source_name)]
    if not items:
        lines.extend(["", text("card", "episodes_empty", locale=locale)])
        return "\n".join(lines)

    for episode in items:
        lines.append("")
        lines.extend(_episode_summary_lines(episode, locale=locale))
    return "\n".join(lines)


def resolve_backend_selector(selector: str | None, backends: list[str]) -> str:
    """Resolve an episode backend while preserving legacy numeric callbacks."""
    return resolve_key_or_legacy_index(selector, backends)


def _episode_keyboard(
    token: str,
    items: list[EpisodeRecord],
    *,
    backends: list[str],
    backend: str,
    view_page: int,
    has_prev: bool,
    has_next: bool,
    locale: str,
    service: EpisodeService,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buttons = [
        InlineKeyboardButton(
            text=str(episode.number),
            callback_data=EpisodeDetailCallback(
                token, backend, episode.number, view_page
            ).encode(),
        )
        for episode in items
    ]
    rows.extend(buttons[index : index + 5] for index in range(0, len(buttons), 5))

    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=KeyedPageCallback(
                    "ap", token, backend, view_page - 1
                ).encode(),
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=text("card", "episodes_page", locale=locale, value=view_page + 1),
            callback_data="noop",
        )
    )
    if has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=KeyedPageCallback(
                    "ap", token, backend, view_page + 1
                ).encode(),
            )
        )
    rows.append(nav)

    source_buttons = [
        InlineKeyboardButton(
            text=("✓ " if candidate == backend else "")
            + service.display_name(candidate),
            callback_data=KeyedPageCallback("ap", token, candidate, 0).encode(),
        )
        for candidate in backends
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


async def edit_episodes_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    view_page: int,
    locale: str,
    backend: str | None = None,
) -> None:
    service = get_app_context().episode_service
    backends = service.available_backends(session.anime.identity)
    if not backends:
        await message.edit_text(
            text=text("card", "episodes_load_failed", locale=locale),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=text("common", "back", locale=locale),
                            callback_data=f"av:{token}:main:0",
                        )
                    ]
                ]
            ),
        )
        return

    backend = resolve_backend_selector(backend, backends)
    source_name = service.display_name(backend)

    view_page = max(0, int(view_page))
    upstream_page, offset = _view_slice(view_page)
    cache_key = (backend, upstream_page)
    page = session.episode_pages.get(cache_key)
    if page is None:
        try:
            page = await service.load_page(
                session.anime.identity,
                page=upstream_page,
                backend=backend,
            )
            session.episode_pages[cache_key] = page
        except Exception:
            logging.exception("Could not load %s episode list", source_name)
            await message.edit_text(
                text=text("card", "episodes_load_failed", locale=locale),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=text("common", "back", locale=locale),
                                callback_data=f"av:{token}:main:0",
                            )
                        ]
                    ]
                ),
            )
            return

    items = page.items[offset : offset + EPISODES_PER_VIEW]
    if not items and view_page > 0:
        view_page -= 1
        upstream_page, offset = _view_slice(view_page)
        cache_key = (backend, upstream_page)
        page = session.episode_pages.get(cache_key) or page
        items = page.items[offset : offset + EPISODES_PER_VIEW]

    has_prev = view_page > 0
    has_next = offset + EPISODES_PER_VIEW < len(page.items) or page.has_next
    content = _episodes_text(items, locale=locale, source_name=source_name)
    keyboard = _episode_keyboard(
        token,
        items,
        backends=backends,
        backend=backend,
        view_page=view_page,
        has_prev=has_prev,
        has_next=has_next,
        locale=locale,
        service=service,
    )

    try:
        await message.edit_text(
            rich_message=InputRichMessage(html=plain_text_to_rich_html(content)),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich episode list edit failed; falling back to text")
        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )


def _duration_text(seconds: int | None, locale: str) -> str | None:
    if seconds is None or seconds <= 0:
        return None
    minutes, remainder = divmod(seconds, 60)
    value = f"{minutes}:{remainder:02d}" if remainder else str(minutes)
    return text("card", "episode_duration", locale=locale, value=value)


def _episode_detail_text(
    episode: EpisodeRecord,
    *,
    locale: str,
    source_name: str,
) -> str:
    lines = [
        text(
            "card",
            "episode_detail_title",
            locale=locale,
            number=episode.number,
            source=source_name,
        ),
        "",
        _episode_title(episode, locale),
    ]
    other_titles = [
        value
        for key in ("english", "romaji", "japanese")
        if (value := (episode.titles.get(key) or "").strip())
        and value != _episode_title(episode, locale)
    ]
    if other_titles:
        lines.append(
            text(
                "card",
                "episode_other_titles",
                locale=locale,
                value=" / ".join(other_titles),
            )
        )
    if episode.aired_at:
        lines.append(
            text(
                "card",
                "episode_date",
                locale=locale,
                value=episode.aired_at.isoformat(),
            )
        )
    duration = _duration_text(episode.duration_seconds, locale)
    if duration:
        lines.append(duration)
    if episode.score is not None:
        lines.append(
            text("card", "episode_score", locale=locale, value=f"{episode.score:g}")
        )
    if episode.filler:
        lines.append(text("card", "episode_filler", locale=locale))
    if episode.recap:
        lines.append(text("card", "episode_recap", locale=locale))
    if episode.synopsis:
        lines.extend(
            ["", text("card", "episode_synopsis", locale=locale), episode.synopsis]
        )
    return "\n".join(lines)


async def edit_episode_detail(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    episode_number: int,
    return_page: int,
    locale: str,
    backend: str = "jikan",
) -> None:
    service = get_app_context().episode_service
    backends = service.available_backends(session.anime.identity)
    if backends:
        backend = resolve_backend_selector(backend, backends)
    elif not backend:
        backend = "jikan"
    source_name = service.display_name(backend)

    cache_key = (backend, int(episode_number))
    episode = session.episode_details.get(cache_key)
    if episode is None:
        try:
            episode = await service.load_episode(
                session.anime.identity,
                episode_number,
                backend=backend,
            )
        except Exception:
            logging.exception("Could not load %s episode detail", source_name)
            episode = None
        if episode is not None:
            session.episode_details[cache_key] = episode

    if episode is None:
        content = text("card", "episode_detail_failed", locale=locale)
        urls: dict[str, str] = {}
    else:
        content = _episode_detail_text(episode, locale=locale, source_name=source_name)
        urls = episode.urls

    rows: list[list[InlineKeyboardButton]] = []
    mal_url = urls.get("MyAnimeList")
    if mal_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=text("card", "open_mal", locale=locale),
                    url=mal_url,
                )
            ]
        )
    anidb_url = urls.get("AniDB")
    if anidb_url:
        rows.append([InlineKeyboardButton(text="AniDB", url=anidb_url)])
    rows.append(
        [
            InlineKeyboardButton(
                text=text("card", "back_to_episodes", locale=locale),
                callback_data=KeyedPageCallback(
                    "ap", token, backend, max(0, return_page)
                ).encode(),
            ),
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=f"av:{token}:main:0",
            ),
        ]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await message.edit_text(
            rich_message=InputRichMessage(html=plain_text_to_rich_html(content)),
            reply_markup=keyboard,
        )
    except Exception:
        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )
