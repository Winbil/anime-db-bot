from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.models import BroadcastSlot, EpisodeReleaseProjection

_JST = timezone(timedelta(hours=9), name="JST")
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_WEEKLY_KINDS = {"tv", "tv_short"}


def _aware_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _next_broadcast_occurrence(
    broadcasts: list[BroadcastSlot],
    *,
    now: datetime,
) -> datetime | None:
    """Return the next weekly broadcast occurrence.

    MAL is currently the only source contributing ``BroadcastSlot`` values. Its
    weekday/time fields describe the Japanese broadcast schedule, so naive clock
    times are interpreted in Asia/Tokyo. A future source can provide a timezone
    directly on ``time`` and it will be preserved.
    """

    now_jst = now.astimezone(_JST)
    candidates: list[datetime] = []
    for slot in broadcasts:
        weekday = _WEEKDAYS.get((slot.weekday or "").strip().casefold())
        if weekday is None or slot.time is None:
            continue
        days = (weekday - now_jst.weekday()) % 7
        target_date = now_jst.date() + timedelta(days=days)
        clock = slot.time
        if clock.tzinfo is None:
            candidate = datetime.combine(target_date, clock, tzinfo=_JST)
        else:
            candidate = datetime.combine(target_date, clock)
        if candidate.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
            candidate += timedelta(days=7)
        candidates.append(candidate)
    return min(
        candidates, default=None, key=lambda value: value.astimezone(timezone.utc)
    )


def build_episode_release_schedule(
    *,
    status: str | None,
    kind: str | None,
    episodes_total: int | None,
    episodes_aired: int | None,
    next_episode_at: datetime | None,
    next_episode_number: int | None,
    broadcasts: list[BroadcastSlot],
    now: datetime | None = None,
) -> list[EpisodeReleaseProjection]:
    """Build a conservative future episode schedule for an airing title.

    The nearest source-provided timestamp is kept as non-estimated data. If no
    source supplies one, a weekly broadcast slot may produce an estimated nearest
    date. Further dates are projected at seven-day intervals only for TV/TV-short
    titles with a known total and next episode number. The projections are
    explicitly marked estimated so UI code never presents them as upstream facts.
    """

    if status != "airing":
        return []

    reference = _aware_now(now)
    first_at = next_episode_at
    first_estimated = False
    if first_at is None:
        first_at = _next_broadcast_occurrence(broadcasts, now=reference)
        first_estimated = first_at is not None
    if first_at is None:
        return []

    first_number = next_episode_number
    if first_number is None and episodes_aired is not None and episodes_aired >= 0:
        first_number = episodes_aired + 1
    if first_number is not None and first_number <= 0:
        first_number = None

    schedule = [
        EpisodeReleaseProjection(
            episode_number=first_number,
            airs_at=first_at,
            estimated=first_estimated,
        )
    ]

    if (
        kind not in _WEEKLY_KINDS
        or episodes_total is None
        or episodes_total <= 0
        or first_number is None
        or first_number >= episodes_total
    ):
        return schedule

    for episode_number in range(first_number + 1, episodes_total + 1):
        schedule.append(
            EpisodeReleaseProjection(
                episode_number=episode_number,
                airs_at=first_at + timedelta(days=7 * (episode_number - first_number)),
                estimated=True,
            )
        )
    return schedule
