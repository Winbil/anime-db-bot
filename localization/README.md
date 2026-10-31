# Localization layer

`localization/` separates canonical vocabulary, source-specific API enums and human-readable interface labels from Python business logic.

## Files

- `data/aliases.json` — aliases used to recognize equivalent genres, roles and studios. Aliases map input text to stable canonical keys and are independent from the UI language.
- `data/source_values.json` — mappings from external API enum values (AniList, MyAnimeList, Shikimori, AniSearch) to stable canonical keys.
- `locales/en.json` — English interface labels and the default/fallback locale.
- `locales/ru.json` — Russian interface labels.
- `locales/ja.json` — Japanese interface labels.
- `locales/de.json` — German interface labels.
- `locales/es.json` — Spanish interface labels.
- `locales/fr.json` — French interface labels.
- `locales/it.json` — Italian interface labels.
- `catalog.py` — cached loader, source-enum normalization and translation API.

## Rules

Source adapters must not own translated dictionaries such as `STATUS_NAMES` or `KIND_NAMES`. External values are mapped through `source_values.json` to locale-neutral keys such as `airing`, `movie`, `spring`, `fantasy` and `light_novel`.

`AnimeRecord` and `AggregatedAnime` keep these canonical values. Translation happens only in a platform renderer for the current user's locale. This means one aggregated card can be rendered in any supported interface language without repeating metadata API requests.

Canonicalization aliases live in `aliases.json`, while algorithms such as normalization, transliteration, identity matching and raw person-name handling stay in Python.

Person names and aliases are stored as raw variants. `display_person_name()` selects and formats them at render time: Russian prefers a Cyrillic display name, Japanese prefers a Japanese/native display name with a Latin alias when available, and English/German/Spanish/French/Italian prefer a Latin display name. This prevents presentation strings from being recursively merged back into aliases.

Dynamic voice credits are stored as internal tokens such as `voice_of::Rimuru Tempest`; the renderer localizes the surrounding `Voice:` label at render time.

Unknown upstream values are preserved instead of being discarded. This keeps the bot forward-compatible when an API introduces a new enum before the catalog is updated.

## Supported interface languages

The supported interface locales are:

- `en` — English (default and fallback);
- `ru` — Русский;
- `ja` — 日本語;
- `de` — Deutsch;
- `es` — Español;
- `fr` — Français;
- `it` — Italiano.

Telegram users change the locale through `/settings`. The choice is stored by platform and user ID in the user-settings repository and therefore survives process restarts.

Each supported locale has a complete catalog with the same key/placeholder contract as English. Missing or invalid locale values still fail safely to the English fallback.

## Source-provided localized text

The bot localizes its own UI and normalized metadata vocabulary. Free-form text supplied by a source is **not machine-translated at runtime**.

AniSearch is the first source that gives the project a direct product reason to maintain the four additional Western locales. Its adapter consumes the supported `en`, `ja`, `de`, `es`, `fr`, and `it` release data. Localized titles and synonyms are kept under language-specific title keys; episode titles follow the same keys; source-provided descriptions are preserved per locale and the renderer selects the current UI language with English fallback; non-Japanese release publishers contribute regional licensors; and voice credits keep Japanese as the untagged original-language baseline while dub roles carry `[EN]`, `[DE]`, `[ES]`, `[FR]`, or `[IT]` suffixes.

Source text remains exactly source-provided apart from the existing safe HTML/text cleanup. Switching the bot UI language changes interface labels and title preference; it does not fabricate translations for a source that did not supply that language.
