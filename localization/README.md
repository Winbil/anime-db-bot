# Localization layer

`localization/` separates canonical vocabulary, source-specific API enums and human-readable interface labels from Python business logic.

## Files

- `data/aliases.json` — aliases used to recognize equivalent genres, roles and studios. Aliases map input text to stable canonical keys and are independent from the UI language.
- `data/source_values.json` — mappings from external API enum values (AniList, MyAnimeList, Shikimori) to stable canonical keys.
- `locales/ru.json` — Russian interface labels.
- `locales/en.json` — English interface labels.
- `locales/ja.json` — Japanese interface labels.
- `catalog.py` — cached loader, source-enum normalization and translation API.

## Rules

Source adapters must not own translated dictionaries such as `STATUS_NAMES` or `KIND_NAMES`. External values are mapped through `source_values.json` to locale-neutral keys such as `airing`, `movie`, `spring`, `fantasy` and `light_novel`.

`AnimeRecord` and `AggregatedAnime` keep these canonical values. Translation happens only in a platform renderer for the current user's locale. This means one aggregated card can be rendered in Russian, English or Japanese without repeating metadata API requests.

Canonicalization aliases live in `aliases.json`, while algorithms such as normalization, transliteration, identity matching and raw person-name handling stay in Python.

Person names and aliases are stored as raw variants. `display_person_name()` selects and formats them at render time: Russian prefers a Cyrillic display name, English prefers a Latin display name, and Japanese prefers a Japanese/native display name with a Latin alias when available. This prevents presentation strings from being recursively merged back into aliases.

Dynamic voice credits are stored as internal tokens such as `voice_of::Rimuru Tempest`; the renderer turns them into `Озвучка: Rimuru Tempest`, `Voice: Rimuru Tempest` or `声: Rimuru Tempest`.

Unknown upstream values are preserved instead of being discarded. This keeps the bot forward-compatible when an API introduces a new enum before the catalog is updated.

## Supported interface languages

The supported interface locales are:

- `ru` — Русский;
- `en` — English;
- `ja` — 日本語.

Telegram users change the locale through `/settings`. The choice is stored by platform and user ID in the user-settings repository and therefore survives process restarts.

Additional interface languages should only be added when there is a real product/source-data reason to maintain them; adding another JSON file alone is not treated as a complete localization.

## Source-provided text

The bot localizes its own UI and normalized metadata vocabulary. Free-form text supplied by a source, such as an anime description, is kept in the language returned by that source and is **not machine-translated**. Users can still switch the description source where the UI exposes source selection.
