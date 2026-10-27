from __future__ import annotations

STANDARD_MESSAGE_LIMIT = 3900
RICH_MESSAGE_LIMIT = 32000
MAX_ANIME_SESSIONS = 200

SECTION_LABELS = {
    "main": "section_main",
    "titles": "section_titles",
    "description": "section_description",
    "popularity": "section_popularity",
    "episodes": "section_episodes",
    "trailers": "section_trailers",
    "links": "section_links",
    "staff": "section_staff",
    "voices": "section_voices",
}

SOURCE_SELECTABLE_SECTIONS = {"titles", "staff", "voices", "popularity"}

ALL_SOURCE_LABELS = {
    "titles": "all_titles",
    "staff": "all_staff",
    "voices": "all_voices",
}
