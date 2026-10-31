from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IMDbRating:
    """Normalized IMDb rating supplement for one confirmed IMDb title ID."""

    imdb_id: str
    rating: float
    votes: int
    url: str
    backend: str
