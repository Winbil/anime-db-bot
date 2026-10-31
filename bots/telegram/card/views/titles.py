from __future__ import annotations

import html

from bots.telegram.card.views.rendering import dedupe_strings
from localization import text


ALL_TITLE_KEYS = (
    "russian",
    "licensed_ru",
    "romaji",
    "english",
    "japanese",
    "german",
    "spanish",
    "french",
    "italian",
)
_LOCALE_TITLE_KEY = {
    "ru": "russian",
    "en": "english",
    "ja": "japanese",
    "de": "german",
    "es": "spanish",
    "fr": "french",
    "it": "italian",
}


def preferred_title_keys(locale: str) -> tuple[str, ...]:
    preferred: tuple[str, ...]
    if locale == "ru":
        preferred = ("russian", "licensed_ru", "romaji", "english", "japanese")
    elif locale == "ja":
        preferred = ("japanese", "romaji", "english", "russian", "licensed_ru")
    elif locale == "en":
        preferred = ("english", "romaji", "japanese", "russian", "licensed_ru")
    else:
        localized = _LOCALE_TITLE_KEY.get(locale)
        preferred = tuple(
            key
            for key in (
                localized,
                "romaji",
                "english",
                "japanese",
                "russian",
                "licensed_ru",
            )
            if key
        )
    return tuple(dict.fromkeys((*preferred, *ALL_TITLE_KEYS)))


def _title_rows(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    locale: str,
) -> list[tuple[str, str]]:
    labels = {
        "russian": text("card", "title_russian", locale=locale),
        "romaji": text("card", "title_romaji", locale=locale),
        "english": text("card", "title_english", locale=locale),
        "japanese": text("card", "title_japanese", locale=locale),
        "german": text("card", "title_german", locale=locale),
        "spanish": text("card", "title_spanish", locale=locale),
        "french": text("card", "title_french", locale=locale),
        "italian": text("card", "title_italian", locale=locale),
        "licensed_ru": text("card", "title_licensed_ru", locale=locale),
    }
    rows: list[tuple[str, str]] = []
    seen_titles: set[str] = set()
    for key in preferred_title_keys(locale):
        value = (titles_map.get(key) or "").strip()
        if value and value.casefold() not in seen_titles:
            seen_titles.add(value.casefold())
            rows.append((labels[key], value))

    synonyms = [
        value
        for value in dedupe_strings(synonyms_values)
        if value.casefold() not in seen_titles
    ]
    if synonyms:
        rows.append((text("card", "synonyms", locale=locale), "; ".join(synonyms)))
    return rows


def _titles_table_html(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    locale: str,
    source: str | None = None,
) -> str:
    base_title = text("card", "titles", locale=locale)
    caption = f"{base_title} — {source}" if source else base_title
    rows = _title_rows(titles_map, synonyms_values, locale=locale)
    if not rows:
        return (
            f"<h2>{html.escape(caption)}</h2>"
            f"<p>{html.escape(text('common', 'no_data', locale=locale))}</p>"
        )
    cells = "".join(
        "<tr>"
        f'<th align="left" valign="top">{html.escape(label)}</th>'
        f'<td align="left" valign="top">{html.escape(value)}</td>'
        "</tr>"
        for label, value in rows
    )
    return (
        "<table bordered striped compact>"
        f"<caption><b>{html.escape(caption)}</b></caption>"
        f"{cells}</table>"
    )


def format_titles(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    locale: str,
    source: str | None = None,
) -> str:
    base_title = text("card", "titles", locale=locale)
    title_value = f"{base_title} — {source}:" if source else f"{base_title}:"
    lines = [title_value]
    for label, value in _title_rows(titles_map, synonyms_values, locale=locale):
        lines.append(f"• {label}: {value}")

    if len(lines) == 1:
        lines.append(text("common", "no_data", locale=locale))
    return "\n".join(lines)
