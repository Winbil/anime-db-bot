from __future__ import annotations

import copy
from dataclasses import dataclass, field

from core.models import PersonCredit


@dataclass(slots=True)
class PeopleManifest:
    """Complete lightweight people index plus an optional local portrait pool.

    ``people`` intentionally contains no portraits. ``portrait_pool`` may keep
    source-returned rich records in memory when an upstream API cannot separate
    identity/role metadata from portrait URLs. The Telegram/session layer never
    exposes that pool until a bounded portrait batch is requested.
    """

    people: list[PersonCredit] = field(default_factory=list)
    portrait_pool: list[PersonCredit] = field(default_factory=list)
    portrait_only: bool = False


def without_portraits(values: list[PersonCredit]) -> list[PersonCredit]:
    result = copy.deepcopy(values)
    for person in result:
        person.portraits = {}
    return result


@dataclass(slots=True)
class PeopleBatch:
    """One progressive staff/voice loading step.

    ``next_cursor`` is source-defined and opaque to the Telegram layer.
    ``complete`` tells the UI whether more batches can be requested.  A source
    may return more portrait-less people than the configured portrait budget;
    the budget is intended to cap expensive portrait-bearing records, not names.
    ``total_count`` is optional and only used as a stable display hint when a
    source can know the full people count without loading every portrait batch.
    """

    people: list[PersonCredit] = field(default_factory=list)
    next_cursor: str | None = None
    complete: bool = True
    total_count: int | None = None
