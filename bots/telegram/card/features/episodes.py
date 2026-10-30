from __future__ import annotations

import logging

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from bots.telegram.callbacks import KeyedPageCallback, resolve_key_or_legacy_index
from bots.telegram.card.runtime.state import AnimeCardSession
from bots.telegram.card.views.renderer import (
    edit_standard_text,
    plain_text_to_rich_html,
)
from bots.telegram.card.views.rendering import _table_html
from core.episode_segments import AggregatedEpisodeSegment, EpisodeSegment
from core.models import EpisodeRecord
from localization import text
from services.media.episode_segments import EpisodeSegmentService
from services.media.episodes import EpisodeService
from services.runtime.app_context import get_app_context

EPISODES_PER_VIEW = 1
UPSTREAM_PAGE_SIZE = 100
_SEGMENT_CALLBACK_PREFIX = "segments-"


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


def _episode_reference(episode: EpisodeRecord) -> str:
    if episode.season_number is not None and episode.episode_number is not None:
        return f"S{episode.season_number}E{episode.episode_number}"
    return str(episode.number)


def _skip_kind_label(kind: str, locale: str) -> str:
    key = {
        "intro": "skipdb_intro",
        "recap": "skipdb_recap",
        "outro": "skipdb_outro",
        "preview": "skipdb_preview",
    }.get(kind, "")
    return text("card", key, locale=locale) if key else kind


def _segment_kind_label(kind: str, locale: str) -> str:
    if kind == "opening":
        return "OP"
    if kind == "ending":
        return "ED"
    if kind == "mixed_opening":
        return "Mixed OP"
    if kind == "mixed_ending":
        return "Mixed ED"
    if kind == "recap":
        return text("card", "skipdb_recap", locale=locale)
    if kind == "preview":
        return text("card", "skipdb_preview", locale=locale)
    return kind.replace("_", " ").strip().title() or "?"


def _timestamp_ms(value: int | None) -> str:
    if value is None or value < 0:
        return "?"
    return _timestamp_seconds(value / 1000)


def _timestamp_seconds(value: float | None) -> str:
    if value is None or value < 0:
        return "?"
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:04.1f}"
    return f"{minutes}:{seconds:04.1f}"


def _segment_range(start: float | None, end: float | None) -> str:
    return f"{_timestamp_seconds(start)}–{_timestamp_seconds(end)}"


def _episode_summary_lines(episode: EpisodeRecord, *, locale: str) -> list[str]:
    title = _episode_title(episode, locale)
    lines = [f"{_episode_reference(episode)}. {title}"]
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
    if episode.backend == "skipdb":
        if episode.skip_types:
            labels = ", ".join(
                _skip_kind_label(kind, locale) for kind in episode.skip_types
            )
            lines.append(text("card", "skipdb_available", locale=locale, value=labels))
        elif episode.skip_intro_absent:
            lines.append(text("card", "skipdb_intro_absent", locale=locale))
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
    segment_backends: list[str],
    segment_backend: str,
    view_page: int,
    has_prev: bool,
    has_next: bool,
    locale: str,
    service: EpisodeService,
    segment_service: EpisodeSegmentService,
) -> InlineKeyboardMarkup:
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
    center = (
        _episode_reference(items[0])
        if items
        else text("card", "episodes_page", locale=locale, value=view_page + 1)
    )
    nav.append(InlineKeyboardButton(text=center, callback_data="noop"))
    if has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=KeyedPageCallback(
                    "ap", token, backend, view_page + 1
                ).encode(),
            )
        )
    rows: list[list[InlineKeyboardButton]] = [nav]

    source_buttons = [
        InlineKeyboardButton(
            text=("✓ " if candidate == backend else "")
            + service.display_name(candidate),
            callback_data=KeyedPageCallback(
                "ap", token, candidate, view_page
            ).encode(),
        )
        for candidate in backends
    ]
    rows.extend(
        source_buttons[index : index + 2] for index in range(0, len(source_buttons), 2)
    )

    if segment_backends:
        all_label = f"⏱ {text('search_ui', 'all', locale=locale)}"
        segment_buttons = [
            InlineKeyboardButton(
                text=("✓ " if segment_backend == "all" else "") + all_label,
                callback_data=KeyedPageCallback(
                    "ap", token, f"{_SEGMENT_CALLBACK_PREFIX}all", view_page
                ).encode(),
            )
        ]
        segment_buttons.extend(
            InlineKeyboardButton(
                text=("✓ " if segment_backend == candidate else "")
                + f"⏱ {segment_service.display_name(candidate)}",
                callback_data=KeyedPageCallback(
                    "ap",
                    token,
                    f"{_SEGMENT_CALLBACK_PREFIX}{candidate}",
                    view_page,
                ).encode(),
            )
            for candidate in segment_backends
        )
        rows.extend(
            segment_buttons[index : index + 2]
            for index in range(0, len(segment_buttons), 2)
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


def _aggregate_segment_lines(
    values: list[AggregatedEpisodeSegment],
    *,
    locale: str,
    service: EpisodeSegmentService,
) -> list[str]:
    lines: list[str] = []
    for segment in values:
        source_names = ", ".join(service.display_name(key) for key in segment.sources)
        suffix = f" · {source_names}" if source_names else ""
        lines.append(
            f"{_segment_kind_label(segment.kind, locale)}: "
            f"{_segment_range(segment.start_seconds, segment.end_seconds)}{suffix}"
        )
    return lines


def _source_segment_lines(
    values: list[EpisodeSegment],
    *,
    locale: str,
) -> list[str]:
    return [
        f"{_segment_kind_label(segment.kind, locale)}: "
        f"{_segment_range(segment.start_seconds, segment.end_seconds)}"
        for segment in values
    ]


async def _episode_timecodes(
    session: AnimeCardSession,
    *,
    episode_number: int,
    episode_length_seconds: int | None,
    locale: str,
) -> tuple[str, str, list[str], str]:
    service = get_app_context().episode_segment_service
    available = service.available_backends(session.anime.identity)
    selected = session.episode_segment_backend
    if selected != "all" and selected not in available:
        selected = "all"
        session.episode_segment_backend = "all"
    if not available:
        return "", "", available, selected

    if selected == "all":
        values, _errors = await service.load_aggregated(
            session.anime.identity,
            episode_number,
            episode_length_seconds=episode_length_seconds,
        )
        lines = _aggregate_segment_lines(values, locale=locale, service=service)
        caption = f"⏱ {text('search_ui', 'all', locale=locale)}"
    else:
        try:
            source_values = await service.load_segments(
                session.anime.identity,
                episode_number,
                backend=selected,
                episode_length_seconds=episode_length_seconds,
            )
        except Exception:
            logging.exception(
                "Could not load %s timestamps",
                service.display_name(selected),
            )
            source_values = []
        lines = _source_segment_lines(source_values, locale=locale)
        caption = f"⏱ {service.display_name(selected)}"

    rendered_lines = lines or [text("common", "no_data", locale=locale)]
    plain = "\n".join([caption, *rendered_lines])
    rich_html = _table_html(caption, rendered_lines)
    return plain, rich_html, available, selected


async def edit_episodes_view(
    message: Message,
    token: str,
    session: AnimeCardSession,
    *,
    view_page: int,
    locale: str,
    backend: str | None = None,
) -> None:
    context = get_app_context()
    service = context.episode_service
    segment_service = context.episode_segment_service
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

    segment_selector: str | None = None
    if backend and backend.startswith(_SEGMENT_CALLBACK_PREFIX):
        segment_selector = backend.removeprefix(_SEGMENT_CALLBACK_PREFIX)
        backend = session.episode_backend

    if backend is None and session.episode_backend in backends:
        backend = session.episode_backend
    backend = resolve_backend_selector(backend, backends)
    source_name = service.display_name(backend)
    session.episode_backend = backend

    segment_backends = segment_service.available_backends(session.anime.identity)
    if segment_selector is not None:
        if segment_selector != "all" and segment_selector not in segment_backends:
            raise ValueError(f"Timestamp backend is unavailable: {segment_selector}")
        session.episode_segment_backend = segment_selector
    if (
        session.episode_segment_backend != "all"
        and session.episode_segment_backend not in segment_backends
    ):
        session.episode_segment_backend = "all"

    view_page = max(0, int(view_page))
    upstream_page, offset = _view_slice(view_page)

    async def load_page(page_number: int):
        cache_key = (backend, page_number)
        cached = session.episode_pages.get(cache_key)
        if cached is not None:
            return cached
        loaded = await service.load_page(
            session.anime.identity,
            page=page_number,
            backend=backend,
        )
        session.episode_pages[cache_key] = loaded
        return loaded

    try:
        page = await load_page(upstream_page)
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
        target_upstream = min(upstream_page, max(1, page.last_visible_page))
        if target_upstream != upstream_page:
            try:
                page = await load_page(target_upstream)
            except Exception:
                logging.exception("Could not load final %s episode page", source_name)
        if page.items:
            offset = min(offset if target_upstream == upstream_page else len(page.items) - 1, len(page.items) - 1)
            view_page = (target_upstream - 1) * UPSTREAM_PAGE_SIZE + offset
            items = page.items[offset : offset + EPISODES_PER_VIEW]

    has_prev = view_page > 0
    has_next = offset + EPISODES_PER_VIEW < len(page.items) or page.has_next
    session.episode_view_page = view_page

    episode: EpisodeRecord | None = items[0] if items else None
    if episode is not None:
        detail_key = (backend, int(episode.number))
        detailed = session.episode_details.get(detail_key)
        if detailed is None:
            try:
                detailed = await service.load_episode(
                    session.anime.identity,
                    episode.number,
                    backend=backend,
                )
            except Exception:
                logging.exception("Could not load %s episode detail", source_name)
            if detailed is not None:
                session.episode_details[detail_key] = detailed
        if detailed is not None:
            episode = detailed

    timecode_plain = ""
    timecode_html = ""
    selected_segment_backend = session.episode_segment_backend
    if episode is None:
        content = _episodes_text([], locale=locale, source_name=source_name)
    else:
        content = _episode_detail_text(episode, locale=locale, source_name=source_name)
        (
            timecode_plain,
            timecode_html,
            segment_backends,
            selected_segment_backend,
        ) = await _episode_timecodes(
            session,
            episode_number=view_page + 1,
            episode_length_seconds=episode.duration_seconds,
            locale=locale,
        )
        if timecode_plain:
            content = f"{content}\n\n{timecode_plain}"

    keyboard = _episode_keyboard(
        token,
        items,
        backends=backends,
        backend=backend,
        segment_backends=segment_backends,
        segment_backend=selected_segment_backend,
        view_page=view_page,
        has_prev=has_prev,
        has_next=has_next,
        locale=locale,
        service=service,
        segment_service=segment_service,
    )

    try:
        detail_text = content
        if timecode_plain:
            detail_text = content[: -(len(timecode_plain) + 2)]
        await message.edit_text(
            rich_message=InputRichMessage(
                html=plain_text_to_rich_html(detail_text) + timecode_html
            ),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich episode edit failed; falling back to text")
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
            number=_episode_reference(episode),
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
    if episode.backend == "skipdb":
        lines.extend(["", text("card", "skipdb_segments", locale=locale)])
        if episode.skip_intro_absent:
            lines.append(text("card", "skipdb_intro_absent", locale=locale))
        for kind in ("intro", "recap", "outro", "preview"):
            segment = episode.skip_segments.get(kind)
            if segment is None:
                continue
            confidence = (
                f"{round(segment.confidence * 100)}%"
                if segment.confidence is not None
                else "—"
            )
            lines.append(
                text(
                    "card",
                    "skipdb_segment",
                    locale=locale,
                    kind=_skip_kind_label(kind, locale),
                    start=_timestamp_ms(segment.start_ms),
                    end=_timestamp_ms(segment.end_ms),
                    confidence=confidence,
                )
            )
        if not episode.skip_segments and not episode.skip_intro_absent:
            lines.append(text("card", "skipdb_no_segments", locale=locale))
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
    skipdb_url = urls.get("SkipDB")
    if skipdb_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=text("card", "open_skipdb", locale=locale),
                    url=skipdb_url,
                )
            ]
        )
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
