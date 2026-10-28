from __future__ import annotations

import math
from statistics import fmean
from typing import Iterable, Mapping


def normalize_source_scores(values: Mapping[str, object]) -> dict[str, float]:
    """Keep only finite source scores on the shared 0..10 scale.

    Invalid values are removed before both the aggregate score and source count
    are computed, so malformed provider data cannot skew either field.
    """
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
