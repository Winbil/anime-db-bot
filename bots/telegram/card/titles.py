from __future__ import annotations

import html

from bots.telegram.card.rendering import dedupe_strings
from localization import text


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
        "licensed_ru": text("card", "title_licensed_ru", locale=locale),
    }
    rows: list[tuple[str, str]] = []
    seen_titles: set[str] = set()
    for key in ("russian", "romaji", "english", "japanese", "licensed_ru"):
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
