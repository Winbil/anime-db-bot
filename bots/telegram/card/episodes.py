from __future__ import annotations

import html
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, Message

from bots.telegram.card.renderer import plain_text_to_rich_html, split_text
from bots.telegram.card.state import AnimeCardSession
from core.models import EpisodeRecord
from localization import text
from sources.jikan import JIKAN_DISPLAY_NAME, JikanSource

EPISODES_PER_VIEW = 10
JIKAN_PAGE_SIZE = 100
JIKAN_SOURCE = JikanSource()


def _view_slice(view_page: int) -> tuple[int, int]:
    view_page = max(0, int(view_page))
    views_per_jikan_page = max(1, JIKAN_PAGE_SIZE // EPISODES_PER_VIEW)
    upstream_page = view_page // views_per_jikan_page + 1
    offset = (view_page % views_per_jikan_page) * EPISODES_PER_VIEW
    return upstream_page, offset


def _episode_title(episode: EpisodeRecord, locale: str) -> str:
    order = ("english", "romaji", "japanese") if locale == "en" else (
        "romaji",
        "english",
        "japanese",
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
                value=episode.aired_at[:10],
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


def _episodes_text(items: list[EpisodeRecord], *, locale: str) -> str:
    lines = [text("card", "episodes_title", locale=locale, source=JIKAN_DISPLAY_NAME)]
    if not items:
        lines.extend(["", text("card", "episodes_empty", locale=locale)])
        return "\n".join(lines)

    for episode in items:
        lines.append("")
        lines.extend(_episode_summary_lines(episode, locale=locale))
    return "\n".join(lines)


def _episode_keyboard(
    token: str,
    items: list[EpisodeRecord],
    *,
    view_page: int,
    has_prev: bool,
    has_next: bool,
    locale: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buttons = [
        InlineKeyboardButton(
            text=str(episode.number),
            callback_data=f"ae:{token}:{episode.number}:{view_page}",
        )
        for episode in items
    ]
    rows.extend(buttons[index:index + 5] for index in range(0, len(buttons), 5))

    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"av:{token}:episodes:{view_page - 1}",
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
                callback_data=f"av:{token}:episodes:{view_page + 1}",
            )
        )
    rows.append(nav)
    rows.append([
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
            callback_data=f"av:{token}:main:0",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def edit_episodes_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    view_page: int,
    locale: str,
) -> None:
    mal_id = str(session.anime.external_ids.get("mal") or "").strip()
    if not mal_id.isdigit():
        await message.edit_text(
            text=text("card", "episodes_need_mal", locale=locale),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text=text("common", "back", locale=locale),
                        callback_data=f"av:{token}:main:0",
                    )
                ]]
            ),
        )
        return

    view_page = max(0, int(view_page))
    upstream_page, offset = _view_slice(view_page)
    page = session.episode_pages.get(upstream_page)
    if page is None:
        try:
            page = await JIKAN_SOURCE.load_episode_page(
                session.anime.identity,
                page=upstream_page,
            )
            session.episode_pages[upstream_page] = page
        except Exception:
            logging.exception("Could not load Jikan/MAL episode list")
            await message.edit_text(
                text=text("card", "episodes_load_failed", locale=locale),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text=text("common", "back", locale=locale),
                            callback_data=f"av:{token}:main:0",
                        )
                    ]]
                ),
            )
            return

    items = page.items[offset:offset + EPISODES_PER_VIEW]
    if not items and view_page > 0:
        view_page -= 1
        upstream_page, offset = _view_slice(view_page)
        page = session.episode_pages.get(upstream_page) or page
        items = page.items[offset:offset + EPISODES_PER_VIEW]

    has_prev = view_page > 0
    has_next = offset + EPISODES_PER_VIEW < len(page.items) or page.has_next
    content = _episodes_text(items, locale=locale)
    keyboard = _episode_keyboard(
        token,
        items,
        view_page=view_page,
        has_prev=has_prev,
        has_next=has_next,
        locale=locale,
    )

    try:
        await message.edit_text(
            rich_message=InputRichMessage(html=plain_text_to_rich_html(content)),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich episode list edit failed; falling back to text")
        await message.edit_text(
            text=split_text(content, 3900, locale=locale)[0],
            reply_markup=keyboard,
        )


def _duration_text(seconds: int | None, locale: str) -> str | None:
    if seconds is None or seconds <= 0:
        return None
    minutes, remainder = divmod(seconds, 60)
    if remainder:
        value = f"{minutes}:{remainder:02d}"
    else:
        value = str(minutes)
    return text("card", "episode_duration", locale=locale, value=value)


def _episode_detail_text(episode: EpisodeRecord, *, locale: str) -> str:
    lines = [
        text(
            "card",
            "episode_detail_title",
            locale=locale,
            number=episode.number,
            source=JIKAN_DISPLAY_NAME,
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
        lines.append(text("card", "episode_other_titles", locale=locale, value=" / ".join(other_titles)))
    if episode.aired_at:
        lines.append(text("card", "episode_date", locale=locale, value=episode.aired_at[:10]))
    duration = _duration_text(episode.duration_seconds, locale)
    if duration:
        lines.append(duration)
    if episode.filler:
        lines.append(text("card", "episode_filler", locale=locale))
    if episode.recap:
        lines.append(text("card", "episode_recap", locale=locale))
    if episode.synopsis:
        lines.extend(["", text("card", "episode_synopsis", locale=locale), episode.synopsis])
    return "\n".join(lines)


async def edit_episode_detail(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    episode_number: int,
    return_page: int,
    locale: str,
) -> None:
    episode = session.episode_details.get(episode_number)
    if episode is None:
        try:
            episode = await JIKAN_SOURCE.load_episode(session.anime.identity, episode_number)
        except Exception:
            logging.exception("Could not load Jikan/MAL episode detail")
            episode = None
        if episode is not None:
            session.episode_details[episode_number] = episode

    if episode is None:
        content = text("card", "episode_detail_failed", locale=locale)
        urls: dict[str, str] = {}
    else:
        content = _episode_detail_text(episode, locale=locale)
        urls = episode.urls

    rows: list[list[InlineKeyboardButton]] = []
    mal_url = urls.get("MyAnimeList")
    if mal_url:
        rows.append([
            InlineKeyboardButton(
                text=text("card", "open_mal", locale=locale),
                url=mal_url,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text=text("card", "back_to_episodes", locale=locale),
            callback_data=f"av:{token}:episodes:{max(0, return_page)}",
        ),
        InlineKeyboardButton(
            text=text("common", "back", locale=locale),
            callback_data=f"av:{token}:main:0",
        ),
    ])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await message.edit_text(
            rich_message=InputRichMessage(html=plain_text_to_rich_html(content)),
            reply_markup=keyboard,
        )
    except Exception:
        await message.edit_text(
            text=split_text(content, 3900, locale=locale)[0],
            reply_markup=keyboard,
        )
