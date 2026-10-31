from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from bots.telegram.callbacks import KeyedPageCallback, resolve_key_or_legacy_index
from bots.telegram.card.runtime.state import AnimeCardSession
from bots.telegram.card.views.release_schedule import format_release_projection
from bots.telegram.card.views.renderer import (
    edit_standard_text,
    plain_text_to_rich_html,
)
from bots.telegram.card.views.rendering import _table_html
from bots.telegram.card.views.titles import preferred_title_keys
from bots.telegram.pagination import card_picker_callback
from core.episode_segments import AggregatedEpisodeSegment, EpisodeSegment
from core.models import AggregatedAnime, EpisodeRecord, EpisodeReleaseProjection
from localization import text
from services.media.episode_segments import EpisodeSegmentService
from services.media.episodes import EpisodeService
from services.runtime.app_context import get_app_context

EPISODES_PER_VIEW = 1
UPSTREAM_PAGE_SIZE = 100
_SEGMENT_CALLBACK_PREFIX = "segments-"
_INITIAL_TIMECODE_WAIT_SECONDS = 0.15


@dataclass(slots=True)
class _EpisodeGroup:
    key: str
    kind: str
    start: int
    end: int
    season_number: int | None = None
    cour_number: int | None = None

    @property
    def count(self) -> int:
        return self.end - self.start + 1


def _positive_number(value: int | None) -> int | None:
    return value if value is not None and value > 0 else None


def _episode_group_signature(
    episode: EpisodeRecord,
) -> tuple[str, int | None, int | None]:
    kind = (episode.episode_kind or "regular").strip().casefold()
    if kind != "regular":
        return "specials", None, None
    season = _positive_number(episode.season_number)
    cour = _positive_number(episode.cour_number)
    if season is not None and cour is not None:
        return "season_cour", season, cour
    if season is not None:
        return "season", season, None
    if cour is not None:
        return "cour", None, cour
    return "main", None, None


def _episode_groups(items: list[EpisodeRecord]) -> list[_EpisodeGroup]:
    groups: list[_EpisodeGroup] = []
    for index, episode in enumerate(items):
        kind, season, cour = _episode_group_signature(episode)
        key = "specials" if kind == "specials" else f"s{season or 0}c{cour or 0}:{kind}"
        if groups and groups[-1].key == key:
            groups[-1].end = index
            continue
        groups.append(
            _EpisodeGroup(
                key=key,
                kind=kind,
                start=index,
                end=index,
                season_number=season,
                cour_number=cour,
            )
        )
    # A single regular season/group would only add UI noise. The hierarchy is
    # shown when it actually lets the user choose between distinct groups.
    return groups if len(groups) > 1 else []


def _episode_group_for_page(
    groups: list[_EpisodeGroup], view_page: int
) -> _EpisodeGroup | None:
    return next(
        (group for group in groups if group.start <= view_page <= group.end),
        None,
    )


def _episode_group_label(group: _EpisodeGroup, *, locale: str) -> str:
    if group.kind == "specials":
        return text("card", "episode_group_specials", locale=locale)
    if group.kind == "season_cour":
        return text(
            "card",
            "episode_group_season_cour",
            locale=locale,
            season=group.season_number,
            cour=group.cour_number,
        )
    if group.kind == "season":
        return text(
            "card",
            "episode_group_season",
            locale=locale,
            number=group.season_number,
        )
    if group.kind == "cour":
        return text(
            "card",
            "episode_group_cour",
            locale=locale,
            number=group.cour_number,
        )
    return text("card", "episode_group_main", locale=locale)


def _view_slice(view_page: int) -> tuple[int, int]:
    view_page = max(0, int(view_page))
    views_per_upstream_page = max(1, UPSTREAM_PAGE_SIZE // EPISODES_PER_VIEW)
    upstream_page = view_page // views_per_upstream_page + 1
    offset = (view_page % views_per_upstream_page) * EPISODES_PER_VIEW
    return upstream_page, offset


def _episode_title(episode: EpisodeRecord, locale: str) -> str:
    for key in preferred_title_keys(locale):
        value = (episode.titles.get(key) or "").strip()
        if value:
            return value
    return text("card", "episode_untitled", locale=locale)


def _episode_reference(episode: EpisodeRecord) -> str:
    # SkipDB uses an internal selector as ``number`` (for example 10001), so
    # its season/episode pair is the user-facing reference. Ordinary anime
    # episode sources such as Kitsu should keep the simple episode ordinal.
    if (
        episode.backend == "skipdb"
        and episode.season_number is not None
        and episode.episode_number is not None
    ):
        return f"S{episode.season_number}E{episode.episode_number}"
    if episode.episode_number is not None:
        return str(episode.episode_number)
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


def _episode_release_projection(
    anime: AggregatedAnime, episode_number: int
) -> EpisodeReleaseProjection | None:
    return next(
        (
            item
            for item in anime.episode_release_schedule
            if item.episode_number == episode_number
        ),
        None,
    )


def _episode_release_projection_text(
    anime: AggregatedAnime, episode_number: int, *, locale: str
) -> str:
    projection = _episode_release_projection(anime, episode_number)
    if projection is None:
        return ""
    lines = [
        f"{text('card', 'release_schedule_title', locale=locale)}:",
        format_release_projection(projection, locale=locale),
    ]
    if projection.estimated:
        lines.extend(
            ["", text("card", "release_schedule_estimate_note", locale=locale)]
        )
    return "\n".join(lines)


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
    *,
    backends: list[str],
    backend: str,
    segment_backends: list[str],
    segment_backend: str,
    view_page: int,
    total_episodes: int | None,
    has_prev: bool,
    current_episode: int | None = None,
    displayed_episode: int | None = None,
    display_total: int | None = None,
    picker_route: str | None = None,
    picker_index: int | None = None,
    episode_groups: list[_EpisodeGroup] | None = None,
    selected_episode_group: str | None = None,
    source_switch_page: int | None = None,
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
    if current_episode is not None:
        nav_current = max(0, int(current_episode))
    elif displayed_episode is not None:
        nav_current = max(0, int(displayed_episode))
    else:
        nav_current = view_page + 1
    nav_total = display_total if display_total is not None else total_episodes
    center = f"{nav_current}/{nav_total if nav_total else '?'}"
    center_callback = (
        card_picker_callback(
            token,
            picker_route or f"ap~{backend}",
            picker_index if picker_index is not None else view_page,
            nav_total,
        )
        if nav_current > 0 and nav_total and nav_total > 1
        else "noop"
    )
    nav.append(InlineKeyboardButton(text=center, callback_data=center_callback))
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

    if episode_groups:
        group_buttons = [
            InlineKeyboardButton(
                text=("✓ " if group.key == selected_episode_group else "")
                + _episode_group_label(group, locale=locale),
                callback_data=KeyedPageCallback(
                    "ap", token, backend, group.start
                ).encode(),
            )
            for group in episode_groups
        ]
        rows.extend(
            group_buttons[index : index + 2]
            for index in range(0, len(group_buttons), 2)
        )

    source_buttons = [
        InlineKeyboardButton(
            text=("✓ " if candidate == backend else "")
            + service.display_name(candidate),
            callback_data=KeyedPageCallback(
                "ap",
                token,
                candidate,
                view_page if source_switch_page is None else source_switch_page,
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

    # Claim this card render before any network wait. A later click increments the
    # generation and makes this invocation stale, so a slow AniDB/Baha request
    # cannot overwrite a newer source or episode page.
    session.episode_render_generation += 1
    generation = session.episode_render_generation

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
        if session.episode_render_generation != generation:
            return
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

    if session.episode_render_generation != generation:
        return

    source_is_empty = upstream_page == 1 and not page.items and not page.has_next
    if source_is_empty:
        # Metadata may still know the title has N episodes, but this particular
        # episode backend has provided none. Keep that distinction explicit in
        # the UI as 0/N instead of pretending page 1 exists.
        view_page = 0
        offset = 0

    requested_episode_number = view_page + 1
    projection = (
        None
        if source_is_empty
        else _episode_release_projection(session.anime, requested_episode_number)
    )

    items = page.items[offset : offset + EPISODES_PER_VIEW]
    if not items and view_page > 0 and projection is None:
        target_upstream = min(upstream_page, max(1, page.last_visible_page))
        if target_upstream != upstream_page:
            try:
                page = await load_page(target_upstream)
            except Exception:
                logging.exception("Could not load final %s episode page", source_name)
        if page.items:
            offset = min(
                offset if target_upstream == upstream_page else len(page.items) - 1,
                len(page.items) - 1,
            )
            view_page = (target_upstream - 1) * UPSTREAM_PAGE_SIZE + offset
            items = page.items[offset : offset + EPISODES_PER_VIEW]
            requested_episode_number = view_page + 1
            projection = _episode_release_projection(
                session.anime, requested_episode_number
            )

    catalog = session.episode_catalogs.get(backend)
    if catalog is None:
        try:
            catalog = await service.load_catalog(
                session.anime.identity,
                backend=backend,
                first_page=page if page.page == 1 else None,
            )
        except Exception:
            logging.exception("Could not load %s episode structure", source_name)
            catalog = []
        session.episode_catalogs[backend] = catalog
    if not catalog and page.page > 1 and not page.has_next:
        cached_pages = [
            session.episode_pages.get((backend, page_number))
            for page_number in range(1, page.page + 1)
        ]
        if all(cached_page is not None for cached_page in cached_pages):
            catalog = [
                item
                for cached_page in cached_pages
                if cached_page is not None
                for item in cached_page.items
            ]
            session.episode_catalogs[backend] = catalog
    episode_groups = _episode_groups(catalog)
    selected_episode_group = _episode_group_for_page(episode_groups, view_page)

    source_has_next = offset + EPISODES_PER_VIEW < len(page.items) or page.has_next
    has_prev = view_page > 0 and not source_is_empty
    has_projected_next = (
        not source_is_empty
        and _episode_release_projection(session.anime, view_page + 2) is not None
    )
    has_next = source_has_next or has_projected_next
    nav_displayed_episode: int | None = None
    nav_display_total: int | None = None
    nav_picker_route: str | None = None
    nav_picker_index: int | None = None
    if selected_episode_group is not None:
        has_prev = view_page > selected_episode_group.start
        has_next = view_page < selected_episode_group.end
        nav_picker_index = view_page - selected_episode_group.start
        nav_displayed_episode = nav_picker_index + 1
        nav_display_total = selected_episode_group.count
        nav_picker_route = f"apg~{backend}~{selected_episode_group.start}"

    total_episodes = session.anime.episodes_total
    if not page.has_next and not session.anime.episode_release_schedule:
        backend_total = (page.page - 1) * UPSTREAM_PAGE_SIZE + len(page.items)
        if backend_total > 0:
            total_episodes = backend_total
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

    if session.episode_render_generation != generation:
        return

    if episode is not None:
        requested_episode_number = episode.episode_number or requested_episode_number
        projection = (
            _episode_release_projection(session.anime, requested_episode_number)
            if episode.episode_kind == "regular"
            else None
        )
    projection_text = (
        _episode_release_projection_text(
            session.anime, requested_episode_number, locale=locale
        )
        if projection is not None
        else ""
    )
    selected_segment_backend = session.episode_segment_backend
    source_switch_page = view_page
    if episode is not None:
        source_switch_page = (
            max(0, (episode.episode_number or requested_episode_number) - 1)
            if episode.episode_kind == "regular"
            else 0
        )
    if episode is None:
        if projection is None:
            detail_text = _episodes_text([], locale=locale, source_name=source_name)
        else:
            detail_text = "\n".join(
                [
                    text(
                        "card",
                        "episode_detail_title",
                        locale=locale,
                        number=str(requested_episode_number),
                        source=source_name,
                    ),
                    "",
                    text(
                        "card",
                        "episode_title",
                        locale=locale,
                        value=text("card", "episode_untitled", locale=locale),
                    ),
                ]
            )
    else:
        detail_text = _episode_detail_text(
            episode, locale=locale, source_name=source_name
        )

    timecode_plain = ""
    timecode_html = ""
    timecodes_ready = False
    timecode_task: asyncio.Task[tuple[str, str, list[str], str]] | None = None
    if (
        episode is not None
        and episode.episode_kind == "regular"
        and segment_backends
    ):
        timecode_task = asyncio.create_task(
            _episode_timecodes(
                session,
                episode_number=episode.episode_number or requested_episode_number,
                episode_length_seconds=episode.duration_seconds,
                locale=locale,
            )
        )
        done, _pending = await asyncio.wait(
            {timecode_task}, timeout=_INITIAL_TIMECODE_WAIT_SECONDS
        )
        if timecode_task in done:
            (
                timecode_plain,
                timecode_html,
                segment_backends,
                selected_segment_backend,
            ) = await timecode_task
            timecodes_ready = True

    if session.episode_render_generation != generation:
        if timecode_task is not None and not timecode_task.done():
            timecode_task.cancel()
        return

    keyboard_segment_backends = (
        segment_backends if episode is None or episode.episode_kind == "regular" else []
    )
    keyboard = _episode_keyboard(
        token,
        backends=backends,
        backend=backend,
        segment_backends=keyboard_segment_backends,
        segment_backend=selected_segment_backend,
        view_page=view_page,
        total_episodes=total_episodes,
        has_prev=has_prev,
        current_episode=0 if source_is_empty else None,
        displayed_episode=nav_displayed_episode,
        display_total=nav_display_total,
        picker_route=nav_picker_route,
        picker_index=nav_picker_index,
        episode_groups=episode_groups,
        selected_episode_group=(
            selected_episode_group.key if selected_episode_group is not None else None
        ),
        source_switch_page=source_switch_page,
        has_next=has_next,
        locale=locale,
        service=service,
        segment_service=segment_service,
    )

    # Give fast timestamp providers a tiny head start so local/cache hits can be
    # included in the first Telegram edit. Slow network providers still fall
    # back to the two-phase render, keeping episode metadata responsive.
    await _render_episode_view(
        message,
        detail_text=detail_text,
        projection_text=projection_text,
        timecode_plain=timecode_plain,
        timecode_html=timecode_html,
        keyboard=keyboard,
        locale=locale,
        detail_as_table=episode is not None or projection is not None,
    )

    if timecode_task is None or timecodes_ready:
        return

    (
        timecode_plain,
        timecode_html,
        segment_backends,
        selected_segment_backend,
    ) = await timecode_task

    # A newer episode/source click owns the card now. Do not let this older,
    # slower timestamp request overwrite the current page when it finally ends.
    if session.episode_render_generation != generation:
        return

    keyboard_segment_backends = (
        segment_backends if episode is None or episode.episode_kind == "regular" else []
    )
    keyboard = _episode_keyboard(
        token,
        backends=backends,
        backend=backend,
        segment_backends=keyboard_segment_backends,
        segment_backend=selected_segment_backend,
        view_page=view_page,
        total_episodes=total_episodes,
        has_prev=has_prev,
        current_episode=0 if source_is_empty else None,
        displayed_episode=nav_displayed_episode,
        display_total=nav_display_total,
        picker_route=nav_picker_route,
        picker_index=nav_picker_index,
        episode_groups=episode_groups,
        selected_episode_group=(
            selected_episode_group.key if selected_episode_group is not None else None
        ),
        source_switch_page=source_switch_page,
        has_next=has_next,
        locale=locale,
        service=service,
        segment_service=segment_service,
    )
    await _render_episode_view(
        message,
        detail_text=detail_text,
        projection_text=projection_text,
        timecode_plain=timecode_plain,
        timecode_html=timecode_html,
        keyboard=keyboard,
        locale=locale,
        detail_as_table=True,
    )


def _episode_detail_html(detail_text: str) -> str:
    lines = detail_text.splitlines()
    if not lines:
        return ""
    caption = lines[0].strip()
    body = [line.strip() for line in lines[1:] if line.strip()]
    return (
        _table_html(caption, body)
        if caption and body
        else plain_text_to_rich_html(detail_text)
    )


def _message_not_modified(error: TelegramBadRequest) -> bool:
    return "message is not modified" in str(error).casefold()


async def _render_episode_view(
    message: Message,
    *,
    detail_text: str,
    projection_text: str,
    timecode_plain: str,
    timecode_html: str,
    keyboard: InlineKeyboardMarkup,
    locale: str,
    detail_as_table: bool,
) -> None:
    content_blocks = [detail_text]
    if projection_text:
        content_blocks.append(projection_text)
    if timecode_plain:
        content_blocks.append(timecode_plain)
    content = "\n\n".join(content_blocks)

    rich_html = (
        _episode_detail_html(detail_text)
        if detail_as_table
        else plain_text_to_rich_html(detail_text)
    )
    if projection_text:
        rich_html += plain_text_to_rich_html(projection_text)
    if timecode_html:
        rich_html += timecode_html
    try:
        await message.edit_text(
            rich_message=InputRichMessage(html=rich_html),
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        if _message_not_modified(exc):
            return
        logging.exception("Rich episode edit failed; falling back to text")
        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
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
            (
                "episode_detail_title"
                if episode.episode_kind == "regular"
                else "episode_special_detail_title"
            ),
            locale=locale,
            number=_episode_reference(episode),
            source=source_name,
        ),
        "",
        text(
            "card",
            "episode_title",
            locale=locale,
            value=_episode_title(episode, locale),
        ),
    ]
    primary_title = _episode_title(episode, locale)
    other_titles: list[str] = []
    seen_titles = {primary_title.casefold()}
    for key in preferred_title_keys(locale):
        value = (episode.titles.get(key) or "").strip()
        if value and value.casefold() not in seen_titles:
            seen_titles.add(value.casefold())
            other_titles.append(value)
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
            rich_message=InputRichMessage(
                html=_episode_detail_html(content)
                if episode is not None
                else plain_text_to_rich_html(content)
            ),
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        if _message_not_modified(exc):
            return
        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )
    except Exception:
        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )
