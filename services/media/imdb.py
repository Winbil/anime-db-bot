from __future__ import annotations

from core.identity import AnimeIdentity
from core.imdb import IMDbRating
from core.models import AggregatedAnime
from core.score_summary import consensus_score, normalize_source_scores
from mappings.resolver import MappingResolver
from services.runtime.source_health import SourceHealthRegistry
from sources.providers.imdb import IMDbRatingsSource
from sources.runtime.resilient import _retry_call

_SAFE_IDENTITY_PROVIDERS = frozenset(
    {"mal", "anilist", "shikimori", "kitsu", "anidb", "anisearch"}
)


class IMDbRatingService:
    """Apply IMDb as a rating-only supplement without making it metadata authority.

    IMDb mappings are intentionally stricter than the general enriched identity:
    only a direct, unambiguous edge from an anime-native peer ID may select the IMDb
    title. TVDB/TMDB/Simkl-style bridge IDs are excluded because they can represent
    franchise/season/movie groupings rather than the exact anime record.
    """

    def __init__(
        self,
        source: IMDbRatingsSource,
        mapping_resolver: MappingResolver,
        health: SourceHealthRegistry | None = None,
    ) -> None:
        self.source = source
        self._mapping_resolver = mapping_resolver
        self._health = health

    def _confirmed_imdb_id(self, anime: AggregatedAnime) -> str | None:
        safe_identity = AnimeIdentity(
            {
                provider: external_id
                for provider, external_id in anime.external_ids.items()
                if provider in _SAFE_IDENTITY_PROVIDERS
            }
        )
        if safe_identity.is_empty():
            return None
        mapped = self._mapping_resolver.resolve(safe_identity)
        imdb_id = str(mapped.get("imdb") or "").strip().casefold()
        return imdb_id or None

    async def load(self, anime: AggregatedAnime) -> IMDbRating | None:
        imdb_id = self._confirmed_imdb_id(anime)
        if not imdb_id:
            return None
        identity = AnimeIdentity({"imdb": imdb_id})
        return await _retry_call(
            self.source.name,
            "ratings",
            lambda: self.source.load_rating(identity),
            health=self._health,
            health_key="imdb",
        )

    async def enrich(self, anime: AggregatedAnime) -> IMDbRating | None:
        rating = await self.load(anime)
        if rating is None:
            return None
        anime.scores["IMDb"] = rating.rating
        anime.scores = normalize_source_scores(anime.scores)
        anime.score_votes["IMDb"] = rating.votes
        anime.score_average = consensus_score(anime.scores.values())
        anime.score_sources_count = len(anime.scores)
        anime.urls.setdefault("IMDb", rating.url)
        return rating
