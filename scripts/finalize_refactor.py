from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(
            f"{path}: expected {count} occurrence(s), got {actual}: {old[:80]!r}"
        )
    target.write_text(text.replace(old, new, count), encoding="utf-8")


write(
    "core/character_identity.py",
    '''from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


def _clean_provider(value: object) -> str:
    return str(value or "").strip().casefold()


def _clean_id(value: object) -> str:
    return str(value or "").strip()


@dataclass(slots=True)
class CharacterIdentity:
    """Conflict-safe source-local identity for one character.

    Character IDs belong to their own namespace and are never mixed with anime
    or person IDs. A shared provider ID confirms a match; different IDs from the
    same provider are a hard conflict. Name equality is only a presentation
    fallback and never canonical identity evidence.
    """

    external_ids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.external_ids = self._normalize(self.external_ids)

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None) -> "CharacterIdentity":
        return cls(dict(values or {}))

    @staticmethod
    def _normalize(values: Mapping[str, object]) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_provider, raw_id in values.items():
            provider = _clean_provider(raw_provider)
            external_id = _clean_id(raw_id)
            if provider and external_id:
                result[provider] = external_id
        return result

    def conflicts_with(self, other: "CharacterIdentity") -> bool:
        shared = set(self.external_ids) & set(other.external_ids)
        return any(self.external_ids[key] != other.external_ids[key] for key in shared)

    def matches(self, other: "CharacterIdentity") -> bool:
        shared = set(self.external_ids) & set(other.external_ids)
        return bool(shared) and not self.conflicts_with(other)

    def merge_missing(self, values: "CharacterIdentity | Mapping[str, object]") -> None:
        incoming = (
            values.external_ids
            if isinstance(values, CharacterIdentity)
            else self._normalize(values)
        )
        for provider, external_id in incoming.items():
            existing = self.external_ids.get(provider)
            if existing is None:
                self.external_ids[provider] = external_id
            elif existing != external_id:
                continue
''',
)

write(
    "core/score_summary.py",
    '''from __future__ import annotations

import math
from statistics import fmean
from typing import Iterable, Mapping


def normalize_source_scores(values: Mapping[str, object]) -> dict[str, float]:
    """Keep only finite source scores on the shared 0..10 scale."""
    result: dict[str, float] = {}
    for raw_source, raw_score in values.items():
        source = str(raw_source or "").strip()
        if not source:
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if math.isfinite(score) and 0.0 <= score <= 10.0:
            result[source] = score
    return result


def consensus_score(values: Iterable[object]) -> float | None:
    """Return an equal-source arithmetic mean on the common 0..10 scale.

    Audience sizes are deliberately not used as weights: MAL, AniList,
    Shikimori and AniDB user populations overlap and are not independent samples.
    """
    scores: list[float] = []
    for raw_score in values:
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if math.isfinite(score) and 0.0 <= score <= 10.0:
            scores.append(score)
    return round(fmean(scores), 2) if scores else None
''',
)

replace(
    "core/models.py",
    "from core.identity import AnimeIdentity\n",
    "from core.character_identity import CharacterIdentity\nfrom core.identity import AnimeIdentity\n",
)
replace(
    "core/models.py",
    "    portraits: dict[str, list[str]] = field(default_factory=dict)\n\n\n@dataclass(slots=True)\nclass AnimeRecord:",
    "    portraits: dict[str, list[str]] = field(default_factory=dict)\n\n    @property\n    def identity(self) -> CharacterIdentity:\n        return CharacterIdentity.from_mapping(self.external_ids)\n\n\n@dataclass(slots=True)\nclass AnimeRecord:",
)

replace(
    "services/identity_aggregator.py",
    "from core.models import AggregatedAnime, AnimeRecord, PersonCredit, PopularityStats, SearchCandidate\n",
    "from core.models import AggregatedAnime, AnimeRecord, PersonCredit, PopularityStats, SearchCandidate\nfrom core.score_summary import consensus_score, normalize_source_scores\n",
)
replace("services/identity_aggregator.py", "    _average_score,\n", "")
replace(
    "services/identity_aggregator.py",
    "        return AggregatedAnime(\n",
    "        scores = normalize_source_scores(scores)\n\n        return AggregatedAnime(\n",
)
replace(
    "services/identity_aggregator.py",
    "            score_average=_average_score(scores),\n",
    "            score_average=consensus_score(scores.values()),\n",
)
replace(
    "services/aggregation_merge.py",
    '''def _average_score(scores: dict[str, float]) -> float | None:
    values = [value for value in scores.values() if isinstance(value, (int, float))]
    if not values:
        return None
    return round(sum(float(value) for value in values) / len(values), 2)


''',
    "",
)
replace("services/aggregator.py", "    _average_score,\n", "")

characters = ROOT / "bots/telegram/card/characters.py"
text = characters.read_text(encoding="utf-8")
start = text.index("def _merge_characters(")
end = text.index("\n\ndef _source_names", start)
new_merge = '''def _merge_characters(groups: list[list[CharacterRecord]]) -> list[CharacterRecord]:
    merged: list[CharacterRecord] = []
    name_keys_by_index: list[set[str]] = []
    for group in groups:
        for character in group:
            names = _dedupe([character.name, *character.aliases])
            name_keys = person_identity_keys(names)
            identity = character.identity

            match_index = next(
                (
                    index
                    for index, existing in enumerate(merged)
                    if existing.identity.matches(identity)
                ),
                None,
            )
            matched_by_id = match_index is not None
            if match_index is None:
                match_index = next(
                    (
                        index
                        for index, existing in enumerate(merged)
                        if name_keys_by_index[index] & name_keys
                        and not existing.identity.conflicts_with(identity)
                    ),
                    None,
                )

            if match_index is None:
                merged.append(CharacterRecord(
                    name=character.name,
                    role=character.role,
                    aliases=list(character.aliases),
                    external_ids=dict(character.external_ids),
                    portraits={source: list(urls) for source, urls in character.portraits.items()},
                ))
                name_keys_by_index.append(name_keys)
                continue

            existing = merged[match_index]
            all_names = _dedupe([
                existing.name,
                *existing.aliases,
                character.name,
                *character.aliases,
            ])
            existing.aliases = [
                value
                for value in all_names
                if value.casefold() != existing.name.casefold()
            ]
            name_keys_by_index[match_index].update(name_keys)
            if _role_priority(character.role) > _role_priority(existing.role):
                existing.role = character.role
            if matched_by_id:
                merged_identity = existing.identity
                merged_identity.merge_missing(identity)
                existing.external_ids = dict(merged_identity.external_ids)
            elif not existing.external_ids and character.external_ids:
                # A name-only presentation merge may carry one source-local ID,
                # but it must not infer a new cross-provider mapping.
                existing.external_ids = dict(character.external_ids)
            for source_name, urls in character.portraits.items():
                existing.portraits[source_name] = _dedupe([
                    *existing.portraits.get(source_name, []),
                    *urls,
                ])
    return merged
'''
characters.write_text(text[:start] + new_merge + text[end:], encoding="utf-8")

renderer = ROOT / "bots/telegram/card/renderer.py"
text = renderer.read_text(encoding="utf-8")
marker = '''async def send_standard_text(
    message: Message,
    text_value: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    locale: str = "ru",
) -> None:
'''
index = text.index(marker)
helper = '''async def edit_standard_text(
    message: Message,
    text_value: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    locale: str = "ru",
    limit: int = STANDARD_MESSAGE_LIMIT,
) -> None:
    """Edit the callback message without discarding overflow text.

    The keyboard remains on the edited message so subsequent callbacks keep
    targeting one stable message. Overflow chunks are emitted as plain follow-up
    messages instead of being silently truncated.
    """
    chunks = split_text(text_value, limit, locale=locale)
    await message.edit_text(text=chunks[0], reply_markup=reply_markup)
    for chunk in chunks[1:]:
        await message.answer(chunk)


'''
renderer.write_text(text[:index] + helper + text[index:], encoding="utf-8")

replace(
    "bots/telegram/card/renderer.py",
    '''        await message.edit_text(
            text=split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)[0],
            reply_markup=fallback,
        )''',
    '''        await edit_standard_text(
            message,
            text_value,
            reply_markup=fallback,
            locale=locale,
        )''',
)
replace(
    "bots/telegram/card/renderer.py",
    '''        await message.edit_text(
            text=split_text(pages[page], STANDARD_MESSAGE_LIMIT, locale=locale)[0],
            reply_markup=keyboard,
        )''',
    '''        await edit_standard_text(
            message,
            pages[page],
            reply_markup=keyboard,
            locale=locale,
        )''',
    count=2,
)

for path in (
    "bots/telegram/card/characters.py",
    "bots/telegram/card/trailers.py",
    "bots/telegram/card/episodes.py",
    "bots/telegram/people_portraits.py",
):
    target = ROOT / path
    value = target.read_text(encoding="utf-8")
    value = value.replace(
        "from bots.telegram.card.renderer import plain_text_to_rich_html, split_text\n",
        "from bots.telegram.card.renderer import edit_standard_text, plain_text_to_rich_html\n",
    )
    value = value.replace(
        "from bots.telegram.card.renderer import split_text\n",
        "from bots.telegram.card.renderer import edit_standard_text\n",
    )
    target.write_text(value, encoding="utf-8")

replace("bots/telegram/card/characters.py", "from bots.telegram.card.constants import STANDARD_MESSAGE_LIMIT\n", "")
replace(
    "bots/telegram/card/characters.py",
    '''    await message.edit_text(
        text=split_text(content, STANDARD_MESSAGE_LIMIT, locale=locale)[0],
        reply_markup=keyboard,
    )''',
    '''    await edit_standard_text(
        message,
        content,
        reply_markup=keyboard,
        locale=locale,
    )''',
)
replace(
    "bots/telegram/card/trailers.py",
    '''        await message.edit_text(
            text=split_text(content, 3900, locale=locale)[0],
            reply_markup=keyboard,
        )''',
    '''        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )''',
)
replace(
    "bots/telegram/card/episodes.py",
    '''        await message.edit_text(
            text=split_text(content, 3900, locale=locale)[0],
            reply_markup=keyboard,
        )''',
    '''        await edit_standard_text(
            message,
            content,
            reply_markup=keyboard,
            locale=locale,
            limit=3900,
        )''',
    count=2,
)
replace("bots/telegram/people_portraits.py", "from bots.telegram.card.constants import STANDARD_MESSAGE_LIMIT\n", "")
replace(
    "bots/telegram/people_portraits.py",
    '''        await message.edit_text(
            text=split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)[0],
            reply_markup=keyboard,
        )''',
    '''        await edit_standard_text(
            message,
            text_value,
            reply_markup=keyboard,
            locale=locale,
        )''',
)

write(
    "tests/test_score_summary.py",
    '''from __future__ import annotations

import math
import unittest

from core.score_summary import consensus_score, normalize_source_scores


class ScoreSummaryTests(unittest.TestCase):
    def test_equal_source_mean_keeps_sources_neutral(self) -> None:
        self.assertEqual(consensus_score([8.0, 9.0, 7.0]), 8.0)

    def test_invalid_scores_are_removed_from_map_and_count(self) -> None:
        scores = normalize_source_scores({
            "MAL": 8.0,
            "AniList": "9",
            "broken": math.nan,
            "too-high": 11,
            "empty": None,
        })
        self.assertEqual(scores, {"MAL": 8.0, "AniList": 9.0})
        self.assertEqual(consensus_score(scores.values()), 8.5)

    def test_no_valid_scores_returns_none(self) -> None:
        self.assertIsNone(consensus_score([None, "bad", math.inf, -1, 99]))
''',
)
write(
    "tests/test_edit_standard_text.py",
    '''from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bots.telegram.card.renderer import edit_standard_text


class EditStandardTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_overflow_chunks_are_not_discarded(self) -> None:
        message = AsyncMock()
        keyboard = object()
        with patch(
            "bots.telegram.card.renderer.split_text",
            return_value=["first", "second", "third"],
        ):
            await edit_standard_text(
                message,
                "full",
                reply_markup=keyboard,
                locale="ru",
            )
        message.edit_text.assert_awaited_once_with(
            text="first",
            reply_markup=keyboard,
        )
        self.assertEqual(
            [call.args[0] for call in message.answer.await_args_list],
            ["second", "third"],
        )
''',
)

tests = ROOT / "tests/test_characters.py"
text = tests.read_text(encoding="utf-8")
text = text.replace(
    "from core.identity import AnimeIdentity\n",
    "from core.character_identity import CharacterIdentity\nfrom core.identity import AnimeIdentity\n",
    1,
)
identity_tests = '''

class CharacterIdentityTests(unittest.TestCase):
    def test_shared_provider_id_confirms_match(self) -> None:
        left = CharacterIdentity({"anilist": "1"})
        right = CharacterIdentity({"anilist": "1", "shikimori": "2"})
        self.assertTrue(left.matches(right))
        left.merge_missing(right)
        self.assertEqual(left.external_ids, {"anilist": "1", "shikimori": "2"})

    def test_same_provider_different_id_is_conflict(self) -> None:
        left = CharacterIdentity({"anilist": "1"})
        right = CharacterIdentity({"anilist": "9"})
        self.assertTrue(left.conflicts_with(right))
        self.assertFalse(left.matches(right))
'''
text = text.replace(
    "\n\nclass CharacterUiTests(unittest.TestCase):",
    identity_tests + "\n\nclass CharacterUiTests(unittest.TestCase):",
    1,
)
ui_tests = '''    def test_same_name_with_conflicting_source_ids_does_not_merge(self) -> None:
        values = _merge_characters([[
            CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "1"}),
            CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "2"}),
        ]])
        self.assertEqual(len(values), 2)

    def test_name_fallback_does_not_infer_cross_provider_ids(self) -> None:
        values = _merge_characters([
            [CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "1"})],
            [CharacterRecord(name="Cid Kagenou", external_ids={"shikimori": "2"})],
        ])
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].external_ids, {"anilist": "1"})

    def test_shared_character_id_merges_even_when_names_differ(self) -> None:
        values = _merge_characters([
            [CharacterRecord(name="Kagenou, Cid", external_ids={"anilist": "1"})],
            [CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "1"})],
        ])
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].external_ids["anilist"], "1")

'''
text = text.replace(
    "    def test_character_view_has_same_source_and_portrait_navigation_shape(self) -> None:\n",
    ui_tests + "    def test_character_view_has_same_source_and_portrait_navigation_shape(self) -> None:\n",
    1,
)
tests.write_text(text, encoding="utf-8")

readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
text = text.replace(
    "Mappings DB строится потоково из нескольких datasets и остаётся на диске — полный граф не копируется в RAM. Directional manual overrides поддерживают `accept` и `reject`; overrides сохраняются при atomic rebuild.",
    "Mappings DB строится потоково из нескольких datasets и остаётся на диске — полный граф не копируется в RAM. Directional manual overrides поддерживают `accept` и `reject`, сохраняют `author`/timestamp и append-only audit history; overrides и история сохраняются при atomic rebuild.",
)
text = text.replace(
    "`PersonCredit` и `CharacterRecord` — разные domain models. Portraits хранят provenance по source, а не одним плоским URL.",
    "`PersonCredit` и `CharacterRecord` — разные domain models. `CharacterIdentity` хранит только source-local ID персонажа и никогда не смешивается с anime/person identity. Portraits хранят provenance по source, а не одним плоским URL.",
)
text = text.replace(
    "- полноценный `CharacterIdentity`: текущий cross-source character display merge всё ещё использует нормализованные варианты имени и не считается canonical identity;\n",
    "",
)
text = text.replace(
    "- richer audit metadata/history для manual mapping overrides.\n",
    "- admin UI/операционные инструменты для просмотра и управления mapping override history.\n",
)
readme.write_text(text, encoding="utf-8")

# The workflow executing this helper can continue after its own file is deleted.
for path in (
    ".github/workflows/refactor-once.yml",
    ".github/workflows/cleanup-once.yml",
    "scripts/finalize_refactor.py",
):
    target = ROOT / path
    if target.exists():
        target.unlink()
