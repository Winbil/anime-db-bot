from __future__ import annotations

from datetime import datetime

from core.models import AggregatedAnime, EpisodeReleaseProjection
from localization import text

_MONTHS = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "ru": (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ),
    "de": (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
    "es": (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ),
    "fr": (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ),
    "it": (
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ),
}


def _timezone_label(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        return ""
    total_minutes = int(offset.total_seconds() // 60)
    if total_minutes == 0:
        return "UTC"
    sign = "+" if total_minutes > 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    suffix = f":{minutes:02d}" if minutes else ""
    return f"UTC{sign}{hours}{suffix}"


def format_release_datetime(value: datetime, *, locale: str) -> str:
    locale = (locale or "en").split("-", 1)[0].casefold()
    zone = _timezone_label(value)
    time_value = value.strftime("%H:%M")
    if locale == "ja":
        rendered = f"{value.year}年{value.month}月{value.day}日 {time_value}"
    else:
        months = _MONTHS.get(locale, _MONTHS["en"])
        month = months[value.month - 1]
        if locale == "en":
            rendered = f"{month} {value.day}, {value.year}, {time_value}"
        elif locale == "de":
            rendered = f"{value.day}. {month} {value.year}, {time_value}"
        elif locale == "es":
            rendered = f"{value.day} de {month} de {value.year}, {time_value}"
        else:
            rendered = f"{value.day} {month} {value.year}, {time_value}"
    return f"{rendered} ({zone})" if zone else rendered


def _release_value(item: EpisodeReleaseProjection, *, locale: str) -> str:
    return format_release_datetime(item.airs_at, locale=locale)


def format_release_projection(item: EpisodeReleaseProjection, *, locale: str) -> str:
    value = _release_value(item, locale=locale)
    if item.episode_number is None:
        key = (
            "release_schedule_estimated_unknown"
            if item.estimated
            else "release_schedule_source_unknown"
        )
        return text("card", key, locale=locale, value=value)
    key = (
        "release_schedule_estimated_item"
        if item.estimated
        else "release_schedule_source_item"
    )
    return text(
        "card",
        key,
        locale=locale,
        episode=item.episode_number,
        value=value,
    )


def format_release_schedule(anime: AggregatedAnime, *, locale: str) -> str:
    title = text("card", "release_schedule_title", locale=locale)
    if not anime.episode_release_schedule:
        return f"{title}:\n{text('card', 'release_schedule_empty', locale=locale)}"

    lines = [f"{title}:"]
    lines.extend(
        format_release_projection(item, locale=locale)
        for item in anime.episode_release_schedule
    )

    if any(item.estimated for item in anime.episode_release_schedule):
        lines.extend(
            ["", text("card", "release_schedule_estimate_note", locale=locale)]
        )
    return "\n".join(lines)
