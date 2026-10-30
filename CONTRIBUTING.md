# Contributing to anime-db-bot

Thanks for contributing. The project favors small, reviewable changes that preserve its source-independent identity model and conservative cross-database matching rules.

## Before you start

- Search existing issues before opening a new one.
- Use the bug or feature issue forms for user-visible changes.
- For security-sensitive findings, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
- For large architectural changes, open an issue first so the design can be discussed before implementation.

## Development setup

The canonical development launcher is cross-platform:

```text
git clone https://github.com/Winbil/anime-db-bot.git
cd anime-db-bot
```

Linux / macOS:

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

Windows native:

```powershell
py -3 scripts\project.py setup --dev
py -3 scripts\project.py check
```

The setup command creates `.venv` and missing `.env.d`, `.proxies.d`, and `.user-agents.d` files from committed examples without overwriting existing values. Add `BOT_TOKEN` to `.env.d/telegram.env` only when you want to run the Telegram bot. Never commit `.env`, `.env.d/`, `.proxies.d/`, `.user-agents.d/`, tokens, passwords, proxy credentials, API keys, or private deployment details.

The Unix `./scripts/setup.sh` and `./scripts/check.sh` files remain thin convenience wrappers around the same Python launcher.

Useful direct checks use the native virtual-environment Python (`.venv/bin/python` on Unix, `.venv\Scripts\python.exe` on Windows).

## Project rules

### Identity and mappings

- No external anime database is globally canonical.
- Never infer cross-database identity from equal numeric IDs.
- Direct-ID lookup must not merge records by title alone.
- Cross-source merges require confirmed identity evidence or the existing constrained search fallback.
- Runtime mapping traversal remains direct-only unless a relation-aware rule is explicitly designed and tested.

### Architecture

Keep search, identity resolution, mappings, source adapters, aggregation, persistence, localization, and platform UI separated. Production dependencies should be composed through `AppContext` rather than introduced as new import-time service singletons.

Heavy capabilities such as people portraits, characters, trailers, and episodes should remain lazy unless there is a measured reason to change that behavior.

### Localization

English is the default and fallback language. User-facing text belongs in the locale catalogs, not as hard-coded presentation strings in Python.

When adding or changing localized UI text:

- update `localization/locales/en.json` first;
- keep Russian and Japanese catalogs in sync;
- preserve the same format placeholders in every locale;
- keep domain models locale-neutral.

### Tests

Add or update tests for behavior changes. Prefer regression tests that describe the user-visible or architectural contract rather than tests coupled to private implementation details.

## Pull requests

Keep pull requests focused. A good PR description explains:

1. what problem is being solved;
2. what behavior changed;
3. how the change was tested;
4. any migration, compatibility, or deployment impact.

The repository PR template contains the final checklist.

By submitting a contribution for inclusion in this project, you agree that your contribution is licensed under the repository's [Apache License 2.0](LICENSE), unless you explicitly state otherwise before it is accepted.
