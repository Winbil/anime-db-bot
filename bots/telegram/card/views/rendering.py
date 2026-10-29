from __future__ import annotations

import html

from aiogram.types import InputRichMessage

from core.models import AggregatedAnime
from localization import DEFAULT_LOCALE, text


def split_text(
    text_value: str, limit: int, *, locale: str = DEFAULT_LOCALE
) -> list[str]:
    text_value = text_value.strip()
    if not text_value:
        return [text("common", "no_data", locale=locale)]
    if len(text_value) <= limit:
        return [text_value]

    chunks: list[str] = []
    while len(text_value) > limit:
        split_at = text_value.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = text_value.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text_value.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text_value[:split_at].strip())
        text_value = text_value[split_at:].strip()

    if text_value:
        chunks.append(text_value)
    return chunks


def plain_text_to_rich_html(text_value: str) -> str:
    paragraphs: list[str] = []
    for paragraph in text_value.split("\n\n"):
        escaped = html.escape(paragraph).replace("\n", "<br>")
        if escaped:
            paragraphs.append(f"<p>{escaped}</p>")
    return "".join(paragraphs)


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def image_gallery_html(urls: list[str], *, limit: int | None = None) -> str:
    urls = dedupe_strings(urls)
    if limit is not None:
        urls = urls[:limit]
    if not urls:
        return ""
    images = "".join(f'<img src="{html.escape(url, quote=True)}"/>' for url in urls)
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def poster_html(anime: AggregatedAnime) -> str:
    return image_gallery_html(anime.posters, limit=50)


def rich(text_value: str) -> InputRichMessage:
    return InputRichMessage(html=plain_text_to_rich_html(text_value))


def _table_html(caption: str, lines: list[str]) -> str:
    rows: list[str] = []
    for rendered in lines:
        rendered = (rendered or "").strip()
        if not rendered:
            continue
        label, separator, value = rendered.partition(":")
        if separator and label.strip():
            rows.append(
                "<tr>"
                f'<th align="left" valign="top">{html.escape(label.strip())}</th>'
                f'<td align="left" valign="top">{html.escape(value.strip())}</td>'
                "</tr>"
            )
        else:
            rows.append(
                f'<tr><td colspan="2" align="left">{html.escape(rendered)}</td></tr>'
            )

    if not rows:
        return ""
    return (
        "<table bordered striped compact>"
        f"<caption><b>{html.escape(caption)}</b></caption>" + "".join(rows) + "</table>"
    )


def append_block(target: list[str], title_value: str, lines: list[str]) -> None:
    lines = [line for line in lines if line]
    if not lines:
        return
    if target:
        target.append("")
    target.append(f"{title_value}:")
    target.extend(lines)


def format_number(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:,}".replace(",", " ")
