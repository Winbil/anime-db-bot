from __future__ import annotations

import re
import unicodedata


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
WORD_RE = re.compile(r"[^a-zа-яё0-9]+", re.IGNORECASE)
TRAILING_DETAILS_RE = re.compile(r"^(.*?)(\s*\([^)]*\))$")


# A deliberately small, explicit vocabulary is safer than trying to machine-
# translate metadata at runtime. Unknown values are preserved as-is.
GENRE_ALIASES = {
    "action": "Экшен",
    "экшен": "Экшен",
    "боевик": "Экшен",
    "adventure": "Приключения",
    "приключения": "Приключения",
    "comedy": "Комедия",
    "комедия": "Комедия",
    "drama": "Драма",
    "драма": "Драма",
    "ecchi": "Этти",
    "этти": "Этти",
    "fantasy": "Фэнтези",
    "фэнтези": "Фэнтези",
    "horror": "Ужасы",
    "ужасы": "Ужасы",
    "mahou shoujo": "Махо-сёдзё",
    "mahou shojo": "Махо-сёдзё",
    "магия": "Магия",
    "magic": "Магия",
    "mecha": "Меха",
    "меха": "Меха",
    "music": "Музыка",
    "музыка": "Музыка",
    "mystery": "Детектив",
    "детектив": "Детектив",
    "mystery": "Мистика",
    "мистика": "Мистика",
    "psychological": "Психологическое",
    "психологическое": "Психологическое",
    "romance": "Романтика",
    "романтика": "Романтика",
    "sci-fi": "Фантастика",
    "sci fi": "Фантастика",
    "science fiction": "Фантастика",
    "фантастика": "Фантастика",
    "slice of life": "Повседневность",
    "повседневность": "Повседневность",
    "sports": "Спорт",
    "спорт": "Спорт",
    "supernatural": "Сверхъестественное",
    "сверхъестественное": "Сверхъестественное",
    "thriller": "Триллер",
    "триллер": "Триллер",
    "gourmet": "Гурман",
    "гурман": "Гурман",
    "boys love": "Сёнэн-ай",
    "boy's love": "Сёнэн-ай",
    "shounen ai": "Сёнэн-ай",
    "сёнэн-ай": "Сёнэн-ай",
    "girls love": "Сёдзё-ай",
    "girl's love": "Сёдзё-ай",
    "shoujo ai": "Сёдзё-ай",
    "сёдзё-ай": "Сёдзё-ай",
    "award winning": "Отмеченное наградами",
    "отмеченное наградами": "Отмеченное наградами",
    "suspense": "Саспенс",
    "саспенс": "Саспенс",
}


ROLE_ALIASES = {
    "director": "Режиссёр",
    "режиссер": "Режиссёр",
    "режиссёр": "Режиссёр",
    "assistant director": "Ассистент режиссёра",
    "ассистент режиссера": "Ассистент режиссёра",
    "ассистент режиссёра": "Ассистент режиссёра",
    "episode director": "Режиссёр эпизода",
    "режиссер эпизода": "Режиссёр эпизода",
    "режиссёр эпизода": "Режиссёр эпизода",
    "series composition": "Композиция сериала",
    "series composer": "Композиция сериала",
    "композиция сериала": "Композиция сериала",
    "original creator": "Автор оригинала",
    "original story": "Автор оригинала",
    "автор оригинала": "Автор оригинала",
    "creator": "Автор",
    "автор": "Автор",
    "script": "Сценарий",
    "screenplay": "Сценарий",
    "сценарий": "Сценарий",
    "storyboard": "Раскадровка",
    "раскадровка": "Раскадровка",
    "character design": "Дизайн персонажей",
    "character designer": "Дизайн персонажей",
    "дизайн персонажей": "Дизайн персонажей",
    "chief animation director": "Главный режиссёр анимации",
    "главный режиссер анимации": "Главный режиссёр анимации",
    "главный режиссёр анимации": "Главный режиссёр анимации",
    "animation director": "Режиссёр анимации",
    "режиссер анимации": "Режиссёр анимации",
    "режиссёр анимации": "Режиссёр анимации",
    "key animation": "Ключевая анимация",
    "ключевая анимация": "Ключевая анимация",
    "2nd key animation": "Вторая ключевая анимация",
    "second key animation": "Вторая ключевая анимация",
    "вторая ключевая анимация": "Вторая ключевая анимация",
    "in-between animation": "Промежуточная анимация",
    "in between animation": "Промежуточная анимация",
    "промежуточная анимация": "Промежуточная анимация",
    "music": "Музыка",
    "музыка": "Музыка",
    "sound director": "Звукорежиссёр",
    "звукорежиссер": "Звукорежиссёр",
    "звукорежиссёр": "Звукорежиссёр",
    "art director": "Арт-директор",
    "арт-директор": "Арт-директор",
    "director of photography": "Оператор-постановщик",
    "photography director": "Оператор-постановщик",
    "оператор-постановщик": "Оператор-постановщик",
    "editing": "Монтаж",
    "editor": "Монтаж",
    "монтаж": "Монтаж",
    "producer": "Продюсер",
    "продюсер": "Продюсер",
    "executive producer": "Исполнительный продюсер",
    "исполнительный продюсер": "Исполнительный продюсер",
    "associate producer": "Ассоциированный продюсер",
    "animation producer": "Продюсер анимации",
    "production assistant": "Ассистент производства",
    "production manager": "Менеджер производства",
    "planning": "Планирование",
    "mechanical design": "Механический дизайн",
    "mecha design": "Механический дизайн",
    "prop design": "Дизайн реквизита",
    "color design": "Цветовой дизайн",
    "color setting": "Цветовой дизайн",
    "cg director": "CG-режиссёр",
    "3d director": "3D-режиссёр",
    "special effects": "Спецэффекты",
    "background art": "Фоны",
    "theme song performance": "Исполнение темы",
    "theme song composition": "Композитор темы",
    "theme song lyrics": "Текст темы",
    "theme song arrangement": "Аранжировка темы",
    "insert song performance": "Исполнение вставной песни",
    "voice actor": "Сэйю",
    "voice acting": "Сэйю",
    "seiyuu": "Сэйю",
    "сейю": "Сэйю",
    "сэйю": "Сэйю",
}


RU_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def normalize_key(value: str) -> str:
    value = clean_text(value).casefold().replace("ё", "е")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = WORD_RE.sub(" ", value)
    return " ".join(value.split())


def transliterate_ru(value: str) -> str:
    result: list[str] = []
    for char in clean_text(value).casefold():
        result.append(RU_TO_LATIN.get(char, char))
    return "".join(result)


def contains_cyrillic(value: str) -> bool:
    return bool(CYRILLIC_RE.search(value or ""))


def canonical_genre(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    return GENRE_ALIASES.get(normalize_key(cleaned), cleaned)


def canonical_role(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""

    # Preserve useful episode/OP/ED qualifiers while translating the role itself.
    suffix = ""
    base = cleaned
    match = TRAILING_DETAILS_RE.match(cleaned)
    if match:
        base = clean_text(match.group(1))
        suffix = match.group(2)

    translated = ROLE_ALIASES.get(normalize_key(base))
    if translated:
        return f"{translated}{suffix}"
    return cleaned


def person_identity_keys(names: list[str]) -> set[str]:
    keys: set[str] = set()
    for name in names:
        name = clean_text(name)
        if not name or normalize_key(name) in {"неизвестно", "unknown"}:
            continue

        direct = normalize_key(name)
        if direct:
            keys.add(direct)
            tokens = direct.split()
            if len(tokens) >= 2:
                keys.add(" ".join(sorted(tokens)))

        transliterated = normalize_key(transliterate_ru(name))
        if transliterated:
            keys.add(transliterated)
            tokens = transliterated.split()
            if len(tokens) >= 2:
                keys.add(" ".join(sorted(tokens)))
    return keys


def preferred_person_name(names: list[str]) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for value in names:
        value = clean_text(value)
        key = normalize_key(value)
        if value and key and key not in seen:
            seen.add(key)
            unique.append(value)

    if not unique:
        return "Неизвестно"

    for value in unique:
        if contains_cyrillic(value):
            return value
    for value in unique:
        if value.isascii():
            return value
    return unique[0]
