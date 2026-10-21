# Localization layer

`localization/` separates canonical vocabulary, source-specific API enums and human-readable labels from Python business logic.

## Files

- `data/aliases.json` — aliases used to recognize equivalent genres, roles and studios. Aliases map input text to stable canonical keys and are independent from the UI language.
- `data/source_values.json` — mappings from external API enum values (AniList, MyAnimeList, Shikimori) to stable canonical keys.
- `locales/ru.json` — Russian labels for canonical keys.
- `locales/en.json` — English labels for the same keys.
- `catalog.py` — cached loader and lookup API.

## Rules

Source adapters should not own translated dictionaries such as `STATUS_NAMES` or `KIND_NAMES`. External values are mapped through `source_values.json`, then rendered through a locale catalog.

Canonicalization aliases should live in `aliases.json`, while algorithms such as normalization, transliteration and identity matching stay in Python.

Unknown external values are preserved instead of being discarded. This keeps the bot forward-compatible when an upstream API introduces a new enum before the catalog is updated.

## Current migration stage

The default behavior remains Russian so the existing Telegram UI does not change unexpectedly. The catalog API already accepts an explicit locale, for example:

```python
canonical_genre("Action", locale="en")
localize_source_value("mal", "status", "currently_airing", locale="en")
```

The next localization stage is to keep canonical keys in the domain model and translate only in platform renderers using a per-user locale from persistent settings. That change is intentionally separate because it affects models, caches, persistence and every UI platform.
