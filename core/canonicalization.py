from __future__ import annotations

import re
import unicodedata


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
WORD_RE = re.compile(r"[^a-zа-яё0-9]+", re.IGNORECASE)
TRAILING_DETAILS_RE = re.compile(r"^(.*?)(\s*\([^)]*\))$")


# Explicit metadata vocabulary is safer than runtime machine translation.
# Unknown values are preserved as-is.
GENRE_ALIASES = {
    "action": "Экшен",
    "экшен": "Экшен",
    "боевик": "Экшен",
    "adventure": "Приключения",
    "приключения": "Приключения",
    "avant garde": "Авангард",
    "авангард": "Авангард",
    "award winning": "Отмеченное наградами",
    "отмеченное наградами": "Отмеченное наградами",
    "boys love": "Сёнэн-ай",
    "boy s love": "Сёнэн-ай",
    "shounen ai": "Сёнэн-ай",
    "shonen ai": "Сёнэн-ай",
    "сёнэн-ай": "Сёнэн-ай",
    "comedy": "Комедия",
    "комедия": "Комедия",
    "drama": "Драма",
    "драма": "Драма",
    "ecchi": "Этти",
    "этти": "Этти",
    "erotica": "Эротика",
    "эротика": "Эротика",
    "fantasy": "Фэнтези",
    "фэнтези": "Фэнтези",
    "girls love": "Сёдзё-ай",
    "girl s love": "Сёдзё-ай",
    "shoujo ai": "Сёдзё-ай",
    "shojo ai": "Сёдзё-ай",
    "сёдзё-ай": "Сёдзё-ай",
    "gourmet": "Гурман",
    "гурман": "Гурман",
    "hentai": "Хентай",
    "хентай": "Хентай",
    "horror": "Ужасы",
    "ужасы": "Ужасы",
    "mahou shoujo": "Махо-сёдзё",
    "mahou shojo": "Махо-сёдзё",
    "махо сёдзё": "Махо-сёдзё",
    "magic": "Магия",
    "магия": "Магия",
    "mecha": "Меха",
    "меха": "Меха",
    "music": "Музыка",
    "музыка": "Музыка",
    "mystery": "Детектив",
    "detective": "Детектив",
    "детектив": "Детектив",
    "psychological": "Психологическое",
    "психологическое": "Психологическое",
    "reincarnation": "Реинкарнация",
    "реинкарнация": "Реинкарнация",
    "romance": "Романтика",
    "романтика": "Романтика",
    "sci fi": "Фантастика",
    "science fiction": "Фантастика",
    "фантастика": "Фантастика",
    "shounen": "Сёнэн",
    "shonen": "Сёнэн",
    "сёнэн": "Сёнэн",
    "slice of life": "Повседневность",
    "повседневность": "Повседневность",
    "sports": "Спорт",
    "спорт": "Спорт",
    "supernatural": "Сверхъестественное",
    "сверхъестественное": "Сверхъестественное",
    "suspense": "Саспенс",
    "саспенс": "Саспенс",
    "thriller": "Триллер",
    "триллер": "Триллер",
    "historical": "Историческое",
    "историческое": "Историческое",
    "military": "Военное",
    "военное": "Военное",
    "martial arts": "Боевые искусства",
    "боевые искусства": "Боевые искусства",
    "school": "Школа",
    "школа": "Школа",
    "isekai": "Исекай",
    "исекай": "Исекай",
    "vampire": "Вампиры",
    "вампиры": "Вампиры",
    "workplace": "Работа",
    "работа": "Работа",
    "time travel": "Путешествие во времени",
    "путешествие во времени": "Путешествие во времени",
}


ROLE_ALIASES = {
    "director": "Режиссёр",
    "режиссер": "Режиссёр",
    "режиссёр": "Режиссёр",
    "assistant director": "Ассистент режиссёра",
    "assistant episode director": "Ассистент режиссёра",
    "ассистент режиссера": "Ассистент режиссёра",
    "ассистент режиссёра": "Ассистент режиссёра",
    "помощник режиссера": "Ассистент режиссёра",
    "помощник режиссёра": "Ассистент режиссёра",
    "episode director": "Режиссёр эпизодов",
    "режиссер эпизода": "Режиссёр эпизодов",
    "режиссёр эпизода": "Режиссёр эпизодов",
    "режиссер эпизодов": "Режиссёр эпизодов",
    "режиссёр эпизодов": "Режиссёр эпизодов",
    "series composition": "Композиция сериала",
    "series composer": "Композиция сериала",
    "композиция сериала": "Композиция сериала",
    "компоновка серий": "Композиция сериала",
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
    "original character design": "Оригинальный дизайн персонажей",
    "original character designer": "Оригинальный дизайн персонажей",
    "оригинальный дизайн персонажей": "Оригинальный дизайн персонажей",
    "оригинал дизайн персонажей": "Оригинальный дизайн персонажей",
    "chief animation director": "Главный режиссёр анимации",
    "главный режиссер анимации": "Главный режиссёр анимации",
    "главный режиссёр анимации": "Главный режиссёр анимации",
    "chief animator": "Главный аниматор",
    "главный аниматор": "Главный аниматор",
    "animation director": "Режиссёр анимации",
    "режиссер анимации": "Режиссёр анимации",
    "режиссёр анимации": "Режиссёр анимации",
    "key animation": "Ключевая анимация",
    "ключевая анимация": "Ключевая анимация",
    "2nd key animation": "Вторая ключевая анимация",
    "second key animation": "Вторая ключевая анимация",
    "вторая ключевая анимация": "Вторая ключевая анимация",
    "второстепен анимация": "Вторая ключевая анимация",
    "in between animation": "Промежуточная анимация",
    "промежуточная анимация": "Промежуточная анимация",
    "промежуточ анимация": "Промежуточная анимация",
    "music": "Музыка",
    "музыка": "Музыка",
    "sound director": "Звукорежиссёр",
    "звукорежиссер": "Звукорежиссёр",
    "звукорежиссёр": "Звукорежиссёр",
    "sound effects": "Звуковые эффекты",
    "звуковые эффекты": "Звуковые эффекты",
    "art director": "Арт-директор",
    "арт директор": "Арт-директор",
    "director of photography": "Оператор-постановщик",
    "photography director": "Оператор-постановщик",
    "оператор постановщик": "Оператор-постановщик",
    "editing": "Монтаж",
    "editor": "Монтаж",
    "монтаж": "Монтаж",
    "producer": "Продюсер",
    "продюсер": "Продюсер",
    "assistant producer": "Ассистент продюсера",
    "ассистент продюсера": "Ассистент продюсера",
    "executive producer": "Исполнительный продюсер",
    "исполнительный продюсер": "Исполнительный продюсер",
    "исполнительн продюсер": "Исполнительный продюсер",
    "associate producer": "Ассоциированный продюсер",
    "animation producer": "Продюсер анимации",
    "production assistant": "Ассистент производства",
    "production manager": "Менеджер производства",
    "assistant production manager": "Ассистент менеджера производства",
    "planning": "Планирование",
    "mechanical design": "Механический дизайн",
    "mecha design": "Механический дизайн",
    "prop design": "Дизайн реквизита",
    "color design": "Дизайн цвета",
    "color setting": "Дизайн цвета",
    "дизайн цвета": "Дизайн цвета",
    "cg director": "CG-режиссёр",
    "3d director": "3D-режиссёр",
    "special effects": "Спецэффекты",
    "спецэффекты": "Спецэффекты",
    "background art": "Фоновая рисовка",
    "фоновая рисовка": "Фоновая рисовка",
    "theme song performance": "Исполнение темы",
    "исполнение гл муз темы": "Исполнение темы",
    "theme song composition": "Композитор темы",
    "композитор гл муз темы": "Композитор темы",
    "theme song lyrics": "Текст темы",
    "theme song arrangement": "Аранжировка темы",
    "аранжировка гл муз темы": "Аранжировка темы",
    "insert song performance": "Исполнение вставной песни",
    "insert song lyrics": "Текст вставной песни",
    "voice actor": "Сэйю",
    "voice acting": "Сэйю",
    "seiyuu": "Сэйю",
    "сейю": "Сэйю",
    "сэйю": "Сэйю",
}


STUDIO_ALIASES = {
    "8bit": "8bit",
}


LOCALIZATION_ROLE_MARKERS = (
    "adr",
    "dub director",
    "dub script",
    "dubbing",
    "mix engineer",
    "script supervisor",
)

LOCALIZATION_LANGUAGE_MARKERS = (
    "english",
    "brazilian portuguese",
    "latin american spanish",
    "portuguese",
    "spanish",
    "german",
    "italian",
    "french",
    "indonesian",
    "korean",
    "chinese",
)


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


def studio_identity_key(value: str) -> str:
    # Studio names frequently differ only by punctuation: 8bit / 8-bit,
    # A-1 Pictures / A1 Pictures, etc.
    return normalize_key(value).replace(" ", "")


def canonical_studio(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    return STUDIO_ALIASES.get(studio_identity_key(cleaned), cleaned)


def is_localization_role(value: str) -> bool:
    normalized = normalize_key(value)
    if not normalized:
        return False
    if any(marker in normalized for marker in LOCALIZATION_ROLE_MARKERS):
        return True
    # AniList often annotates localization credits with the language in the
    # role text, e.g. "ADR Director (English)".
    return any(marker in normalized for marker in LOCALIZATION_LANGUAGE_MARKERS)


def is_primary_voice_role(value: str) -> bool:
    """Return True only for original/Japanese voice acting roles.

    Shikimori distinguishes foreign dubs as "Сэйю (EN)", "Сэйю (DE)", etc.
    Those should not be mixed into the main seiyuu list.
    """
    normalized = normalize_key(value)
    return normalized in {"сэйю", "сейю", "seiyuu", "voice actor", "voice acting"}


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

    # Prefer a clean Russian display name over an old combined Shikimori string
    # like "Ёхэй Ито (Youhei Itou, 伊藤 洋平)".
    cyrillic = [value for value in unique if contains_cyrillic(value)]
    if cyrillic:
        return min(cyrillic, key=lambda value: (len(value), value.casefold()))

    ascii_names = [value for value in unique if value.isascii()]
    if ascii_names:
        return min(ascii_names, key=lambda value: (len(value), value.casefold()))

    return min(unique, key=lambda value: (len(value), value.casefold()))
