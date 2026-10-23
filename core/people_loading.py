from __future__ import annotations

from dataclasses import dataclass, field

from core.models import PersonCredit


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
