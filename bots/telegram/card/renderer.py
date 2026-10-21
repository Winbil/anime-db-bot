from __future__ import annotations

import html
import logging

from aiogram.types import InlineKeyboardMarkup, InputRichMessage, Message

from bots.telegram.card.constants import RICH_MESSAGE_LIMIT, STANDARD_MESSAGE_LIMIT
from bots.telegram.card.keyboards import (
    description_keyboard,
    fallback_main_keyboard,
    navigation_keyboard,
    source_section_keyboard,
)
from bots.telegram.card.selectors import (
    description_sources,
    ordered_mapping_items,
    source_section_sources,
)
from core.models import AggregatedAnime


def split_text(text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text:
        return ["Нет данных."]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    if text:
        chunks.append(text)
    return chunks


def plain_text_to_rich_html(text: str) -> str:
    paragraphs: list[str] = []
    for paragraph in text.split("\n\n"):
        escaped = html.escape(paragraph).replace("\n", "<br>")
        if escaped:
            paragraphs.append(f"<p>{escaped}</p>")
    return "".join(paragraphs)


def poster_html(anime: AggregatedAnime) -> str:
    urls = anime.posters[:50]
    if not urls:
        return ""
    images = "".join(
        f'<img src="{html.escape(url, quote=True)}"/>'
        for url in urls
    )
    return images if len(urls) == 1 else f"<tg-slideshow>{images}</tg-slideshow>"


def rich(text: str) -> InputRichMessage:
    return InputRichMessage(html=plain_text_to_rich_html(text))


def main_rich(token: str, anime: AggregatedAnime, text: str) -> InputRichMessage:
    links = (
        "<p><b>Подробная информация</b><br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:description:0">Описание</tg-button>'
        " — выбрать источник<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:titles:0">Все названия</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:staff:0">Авторы и команда</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:voices:0">Сэйю</tg-button>'
        " — нажмите, чтобы открыть<br>"
        f'<tg-button type="callback_data" style="link" data="av:{token}:links:0">Ссылки</tg-button>'
        " — выбрать базу</p>"
    )
    return InputRichMessage(
        html=poster_html(anime) + plain_text_to_rich_html(text) + links
    )


async def send_standard_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    chunks = split_text(text, STANDARD_MESSAGE_LIMIT)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


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


def format_number(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:,}".replace(",", " ")


def format_people(title: str, people) -> str:
    if not people:
        return f"{title}:\nНет данных."
    lines = [f"{title}:"]
    for person in people:
        roles = ", ".join(person.roles) if person.roles else "роль не указана"
        lines.append(f"• {person.name} — {roles}")
    return "\n".join(lines)


def format_titles(
    titles_map: dict[str, str],
    synonyms_values: list[str],
    *,
    source: str | None = None,
) -> str:
    title = f"Названия — {source}:" if source else "Названия:"
    lines = [title]
    labels = {
        "russian": "Русское",
        "romaji": "Оригинальное / romaji",
        "english": "English",
        "japanese": "日本語",
        "licensed_ru": "Лицензионное RU",
    }
    seen_titles: set[str] = set()
    for key in ("russian", "romaji", "english", "japanese", "licensed_ru"):
        value = (titles_map.get(key) or "").strip()
        if value and value.casefold() not in seen_titles:
            seen_titles.add(value.casefold())
            lines.append(f"• {labels[key]}: {value}")

    synonyms = [
        value
        for value in dedupe_strings(synonyms_values)
        if value.casefold() not in seen_titles
    ]
    if synonyms:
        lines.append("• Синонимы: " + "; ".join(synonyms))

    if len(lines) == 1:
        lines.append("Нет данных.")
    return "\n".join(lines)


def append_block(target: list[str], title: str, lines: list[str]) -> None:
    lines = [line for line in lines if line]
    if not lines:
        return
    if target:
        target.append("")
    target.append(f"{title}:")
    target.extend(lines)


def source_section_text(
    anime: AggregatedAnime,
    section: str,
    source: str,
) -> str:
    if section == "titles":
        return format_titles(
            anime.titles_by_source.get(source, {}),
            anime.synonyms_by_source.get(source, []),
            source=source,
        )
    if section == "staff":
        return format_people(
            f"Авторы и команда — {source}",
            anime.staff_by_source.get(source, []),
        )
    if section == "voices":
        return format_people(
            f"Сэйю / актёры озвучки — {source}",
            anime.voices_by_source.get(source, []),
        )
    return "Нет данных."


def anime_sections(anime: AggregatedAnime) -> dict[str, str]:
    total = anime.episodes_total or 0
    aired = anime.episodes_aired or 0
    episodes = f"{aired}/{total}" if total else str(aired or "—")

    main = [anime.title]
    basic: list[str] = []
    if anime.kind:
        basic.append(f"Тип: {anime.kind}")
    if anime.status:
        basic.append(f"Статус: {anime.status}")
    basic.append(f"Серии: {episodes}")
    if anime.duration_minutes:
        basic.append(f"Длительность серии: {anime.duration_minutes} мин.")
    if anime.rating:
        basic.append(f"Возрастной рейтинг: {anime.rating}")
    append_block(main, "Основное", basic)

    release: list[str] = []
    if anime.season:
        release.append(f"Сезон: {anime.season}")
    if anime.aired_on or anime.released_on:
        release.append(
            "Начало/Конец показа: "
            f"{anime.aired_on or '—'}/{anime.released_on or '—'}"
        )
    if anime.next_episode_at:
        release.append(f"Следующая серия: {anime.next_episode_at}")
    if anime.broadcasts:
        release.append(f"Расписание: {', '.join(anime.broadcasts)}")
    append_block(main, "Выход", release)

    production: list[str] = []
    if anime.source_materials:
        production.append(f"Первоисточник: {', '.join(anime.source_materials)}")
    if anime.genres:
        production.append(f"Жанры: {', '.join(anime.genres)}")
    if anime.studios:
        production.append(f"Студии: {', '.join(anime.studios)}")
    if anime.licensors:
        production.append(f"Лицензиаты: {', '.join(anime.licensors)}")
    if anime.franchise:
        production.append(f"Франшиза: {anime.franchise}")
    append_block(main, "Производство", production)

    audience: list[str] = []
    if anime.score_average is not None:
        audience.append(
            f"Средняя оценка: {anime.score_average:g} "
            f"(источников: {anime.score_sources_count})"
        )
    for source, score in ordered_mapping_items(anime.scores, anime.sources):
        audience.append(f"{source}: {float(score):g}")
    if anime.rank:
        audience.append(f"Рейтинг: #{anime.rank}")
    if anime.popularity_rank:
        audience.append(f"Популярность: #{anime.popularity_rank}")
    if anime.list_users is not None:
        audience.append(f"В списках пользователей: {format_number(anime.list_users)}")
    if anime.scoring_users is not None:
        audience.append(f"Поставили оценку: {format_number(anime.scoring_users)}")
    if anime.favorites is not None:
        audience.append(f"В избранном: {format_number(anime.favorites)}")
    append_block(main, "Оценка и популярность", audience)

    source_lines: list[str] = []
    if anime.sources:
        source_lines.append(f"Базы данных: {', '.join(anime.sources)}")
    if anime.external_ids:
        ids = " | ".join(
            f"{name.upper()}: {value}" for name, value in anime.external_ids.items()
        )
        source_lines.append(f"ID: {ids}")
    if anime.errors:
        source_lines.append("Недоступны: " + ", ".join(anime.errors))
    append_block(main, "Источники", source_lines)

    description_text = (
        "Описание:\nВыбери источник кнопкой ниже."
        if anime.descriptions
        else "Описание:\nНет доступных описаний."
    )
    links_text = (
        "Ссылки:\nВыбери базу кнопкой ниже."
        if anime.urls
        else "Ссылки:\nНет доступных ссылок."
    )

    return {
        "main": "\n".join(main),
        "titles": format_titles(anime.titles, anime.synonyms),
        "description": description_text,
        "links": links_text,
        "staff": format_people("Авторы и команда", anime.staff),
        "voices": format_people("Сэйю / актёры озвучки", anime.voices),
    }


def view_pages(anime: AggregatedAnime, section: str) -> list[str]:
    return split_text(
        anime_sections(anime).get(section) or "Нет данных.",
        RICH_MESSAGE_LIMIT,
    )


def rich_view(
    token: str,
    anime: AggregatedAnime,
    section: str,
    text: str,
) -> InputRichMessage:
    return main_rich(token, anime, text) if section == "main" else rich(text)


async def send_anime_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str = "main",
    page: int = 0,
) -> None:
    pages = view_pages(anime, section)
    page = max(0, min(page, len(pages) - 1))
    keyboard = navigation_keyboard(token, anime, section, page, len(pages))
    text = pages[page]

    try:
        await message.answer_rich(
            rich_view(token, anime, section, text),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("sendRichMessage failed; falling back to standard sendMessage")
        fallback = fallback_main_keyboard(token) if section == "main" else keyboard
        await send_standard_text(message, text, reply_markup=fallback)


async def edit_anime_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    page: int,
) -> None:
    pages = view_pages(anime, section)
    page = max(0, min(page, len(pages) - 1))
    keyboard = navigation_keyboard(token, anime, section, page, len(pages))
    text = pages[page]

    try:
        await message.edit_text(
            rich_message=rich_view(token, anime, section, text),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich message edit failed; falling back to standard text edit")
        fallback = fallback_main_keyboard(token) if section == "main" else keyboard
        await message.edit_text(
            text=split_text(text, STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=fallback,
        )


async def edit_description_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    source_index: int,
    page: int,
) -> None:
    sources = description_sources(anime)
    if source_index < 0 or source_index >= len(sources):
        raise ValueError("Description source index is out of range")

    source = sources[source_index]
    description = anime.descriptions[source]
    text = f"Описание — {source}\n\n{description}"
    if source == "MyAnimeList" and anime.background:
        text += f"\n\nДополнительная информация:\n{anime.background}"

    pages = split_text(text, RICH_MESSAGE_LIMIT)
    page = max(0, min(page, len(pages) - 1))
    keyboard = description_keyboard(token, source_index, page, len(pages))

    try:
        await message.edit_text(
            rich_message=rich(pages[page]),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich description edit failed; falling back to standard text edit")
        await message.edit_text(
            text=split_text(pages[page], STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=keyboard,
        )


async def edit_source_section_view(
    message: Message,
    token: str,
    anime: AggregatedAnime,
    section: str,
    source_index: int,
    page: int,
) -> None:
    sources = source_section_sources(anime, section)
    if source_index < 0 or source_index >= len(sources):
        raise ValueError("Source section index is out of range")

    source = sources[source_index]
    pages = split_text(
        source_section_text(anime, section, source),
        RICH_MESSAGE_LIMIT,
    )
    page = max(0, min(page, len(pages) - 1))
    keyboard = source_section_keyboard(
        token,
        anime,
        section,
        source_index,
        page,
        len(pages),
    )

    try:
        await message.edit_text(
            rich_message=rich(pages[page]),
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception("Rich source section edit failed; falling back to standard text edit")
        await message.edit_text(
            text=split_text(pages[page], STANDARD_MESSAGE_LIMIT)[0],
            reply_markup=keyboard,
        )
