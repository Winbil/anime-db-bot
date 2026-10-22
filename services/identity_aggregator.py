from __future__ import annotations

import asyncio
import logging

from core.canonicalization import canonical_genre_token
from core.contracts import AnimeSource
from core.identity import AnimeIdentity
from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate
from localization import canonicalize_domain_value
from services.aggregator import (
    AnimeAggregator as _MergeAnimeAggregator,
    _average_score,
    _best_text,
    _clean,
    _consensus_domain,
    _consensus_int,
    _consensus_text,
    _dedupe_strings,
    _max_int,
    _merge_broadcasts,
    _merge_people,
    _merge_season,
    _merge_source_text,
    _merge_studios,
    _min_positive_int,
)
from services.id_resolver import enrich_identity


class AnimeAggregator(_MergeAnimeAggregator):
    """Identity-native metadata aggregation with no mandatory database key.

    Sources are queried with all IDs known at that moment. IDs discovered from
    successful records are merged into the identity graph, then previously
    inapplicable sources get one second pass. This lets an AniList-only or
    Shikimori-only search result expand into other databases without choosing a
    global primary ID.
    """

    def __init__(self, sources: tuple[AnimeSource, ...] | list[AnimeSource]) -> None:
        super().__init__(sources)

    @staticmethod
    def _record_conflict(
        identity: AnimeIdentity,
        record: AnimeRecord,
    ) -> dict[str, tuple[str, str]]:
        return identity.conflicting_ids(record.identity)

    @staticmethod
    def _merge_record_identity(identity: AnimeIdentity, record: AnimeRecord) -> None:
        conflicts = identity.merge_missing(record.identity)
        if conflicts:
            logging.warning(
                "Ignoring conflicting identity edges from %s: %s",
                record.source,
                conflicts,
            )

    async def aggregate(self, candidate: SearchCandidate) -> AggregatedAnime:
        titles_for_resolution = [candidate.title, *candidate.aliases]
        identity = await enrich_identity(candidate.identity, titles_for_resolution)
        if identity.is_empty():
            raise RuntimeError("Search result does not contain any external database ID")

        async def run(source: AnimeSource, current_identity: AnimeIdentity):
            try:
                record = await source.get_details(current_identity.copy())
                return source.name, record, None
            except Exception as exc:
                return source.name, None, f"{type(exc).__name__}: {exc}"

        first_results = await asyncio.gather(
            *(run(source, identity) for source in self._sources)
        )

        records_by_source: dict[str, AnimeRecord] = {}
        errors: dict[str, str] = {}
        unavailable: set[str] = set()

        for source_name, record, error in first_results:
            if error:
                errors[source_name] = error
                continue
            if record is None:
                unavailable.add(source_name)
                continue
            conflicts = self._record_conflict(identity, record)
            if conflicts:
                errors[source_name] = f"identity conflict: {conflicts}"
                continue
            records_by_source[source_name] = record
            self._merge_record_identity(identity, record)

        before_enrichment = identity.fingerprint()
        identity = await enrich_identity(identity, titles_for_resolution)
        identity_expanded = identity.fingerprint() != before_enrichment

        if records_by_source:
            for record in records_by_source.values():
                before = identity.fingerprint()
                self._merge_record_identity(identity, record)
                identity_expanded = identity_expanded or identity.fingerprint() != before

        # A successful source may reveal a new cross-database ID (for example an
        # AniList result can reveal MAL). Give only sources that were simply
        # inapplicable in the first pass one chance with the richer graph.
        if identity_expanded and unavailable:
            retry_sources = [
                source for source in self._sources if source.name in unavailable
            ]
            second_results = await asyncio.gather(
                *(run(source, identity) for source in retry_sources)
            )
            for source_name, record, error in second_results:
                if error:
                    errors[source_name] = error
                    continue
                if record is None:
                    continue
                conflicts = self._record_conflict(identity, record)
                if conflicts:
                    errors[source_name] = f"identity conflict: {conflicts}"
                    continue
                records_by_source[source_name] = record
                self._merge_record_identity(identity, record)

        records = [
            records_by_source[source.name]
            for source in self._sources
            if source.name in records_by_source
        ]
        if not records:
            raise RuntimeError(
                "No metadata source could provide details for identity "
                + identity.describe()
            )

        titles: dict[str, str] = {}
        synonyms: list[str] = [candidate.title, *candidate.aliases]
        scores = dict(candidate.scores)
        descriptions: dict[str, str] = {}
        urls: dict[str, str] = {}
        background_values: list[str] = []
        titles_by_source: dict[str, dict[str, str]] = {}
        synonyms_by_source: dict[str, list[str]] = {}
        staff_by_source: dict[str, list[PersonCredit]] = {}
        voices_by_source: dict[str, list[PersonCredit]] = {}

        for record in records:
            source_titles = {
                key: value
                for key, raw_value in record.titles.items()
                if (value := _clean(raw_value))
            }
            source_synonyms = _dedupe_strings(record.synonyms)
            if source_titles or source_synonyms:
                titles_by_source[record.source] = source_titles
                synonyms_by_source[record.source] = source_synonyms

            source_staff = _merge_people(
                [record.staff],
                drop_localization_roles=True,
            )
            if source_staff:
                staff_by_source[record.source] = source_staff

            source_voices = _merge_people([record.voices])
            if source_voices:
                voices_by_source[record.source] = source_voices

            for key, value in source_titles.items():
                existing = titles.get(key)
                if existing is None:
                    titles[key] = value
                elif existing.casefold() != value.casefold():
                    synonyms.append(value)

            synonyms.extend(source_synonyms)
            self._merge_record_identity(identity, record)

            if record.score is not None:
                scores[record.source] = float(record.score)

            _merge_source_text(descriptions, record.descriptions)
            background_values.extend(record.backgrounds)
            urls.update(record.urls)

        chosen_titles = {value.casefold() for value in titles.values() if value}
        synonyms = [
            value
            for value in _dedupe_strings(synonyms)
            if value.casefold() not in chosen_titles
        ]

        title = (
            titles.get("romaji")
            or titles.get("english")
            or titles.get("japanese")
            or titles.get("russian")
            or candidate.title
        )
        season, season_year = _merge_season(records)
        canonical_genres = _dedupe_strings(
            [
                canonical_genre_token(value)
                for record in records
                for value in record.genres
                if canonical_genre_token(value)
            ]
        )
        source_materials = _dedupe_strings(
            [
                canonicalize_domain_value("source_material", value) or value
                for record in records
                for value in record.source_materials
                if _clean(value)
            ]
        )

        return AggregatedAnime(
            title=title,
            titles=titles,
            synonyms=synonyms,
            external_ids=dict(identity.external_ids),
            sources=_dedupe_strings([record.source for record in records]),
            kind=_consensus_domain(records, "kind", "anime_kind"),
            status=_consensus_domain(records, "status", "anime_status"),
            rating=_consensus_domain(records, "rating", "rating"),
            season=season,
            season_year=season_year,
            franchise=_consensus_text(records, "franchise"),
            episodes_total=_consensus_int(records, "episodes_total", prefer_max_on_tie=True),
            episodes_aired=_max_int(records, "episodes_aired"),
            duration_minutes=_consensus_int(records, "duration_minutes"),
            aired_on=_consensus_text(records, "aired_on"),
            released_on=_consensus_text(records, "released_on"),
            next_episode_at=_consensus_text(records, "next_episode_at"),
            scores=scores,
            score_average=_average_score(scores),
            score_sources_count=len(scores),
            rank=_min_positive_int(records, "rank"),
            popularity_rank=_min_positive_int(records, "popularity_rank"),
            list_users=_max_int(records, "list_users"),
            scoring_users=_max_int(records, "scoring_users"),
            favorites=_max_int(records, "favorites"),
            genres=canonical_genres,
            studios=_merge_studios(records),
            licensors=_dedupe_strings([value for record in records for value in record.licensors]),
            source_materials=source_materials,
            broadcasts=_merge_broadcasts(records),
            titles_by_source=titles_by_source,
            synonyms_by_source=synonyms_by_source,
            staff_by_source=staff_by_source,
            voices_by_source=voices_by_source,
            descriptions=descriptions,
            background=_best_text(background_values),
            posters=_dedupe_strings([value for record in records for value in record.posters]),
            urls=urls,
            staff=_merge_people(
                [record.staff for record in records],
                drop_localization_roles=True,
            ),
            voices=_merge_people([record.voices for record in records]),
            errors=errors,
        )
