from __future__ import annotations

import asyncio
import logging

from core.identity import AnimeIdentity
from core.models import AnimeRecord, SearchCandidate, SearchResultSet
from services.id_resolver import enrich_identity
from services.search import merge_candidates


class DirectIdLookupService:
    """Resolve IDs and enrich confirmed identities across metadata sources."""

    def __init__(self, sources) -> None:
        self._source_map = {
            str(source.source_key).strip().casefold(): source
            for source in sources
            if str(getattr(source, "source_key", "")).strip()
        }
        if not self._source_map:
            raise ValueError("DirectIdLookupService requires keyed metadata sources")

    @property
    def source_keys(self) -> tuple[str, ...]:
        return tuple(self._source_map)

    async def _resolve_identity(
        self,
        identity: AnimeIdentity,
        titles: list[str],
    ) -> AnimeIdentity:
        # The current resolver graph contains MAL -> Shikimori. Do not invoke it
        # in isolated compositions that do not even contain a Shikimori source.
        if "shikimori" not in self._source_map:
            return identity.copy()
        try:
            return (await enrich_identity(identity, titles)).copy()
        except Exception:
            logging.warning(
                "Could not enrich search identity %s",
                identity.describe(),
                exc_info=True,
            )
            return identity.copy()

    async def _records_for_candidate(
        self,
        candidate: SearchCandidate,
    ) -> tuple[AnimeIdentity, list[AnimeRecord]]:
        titles = _dedupe([candidate.title, *candidate.aliases])
        identity = await self._resolve_identity(candidate.identity, titles)
        initial_fingerprint = identity.fingerprint()
        records_by_key: dict[str, AnimeRecord] = {}
        unavailable: set[str] = set()

        async def load(source_key: str, current_identity: AnimeIdentity):
            source = self._source_map[source_key]
            try:
                record = await source.get_details(current_identity.copy())
                return source_key, source, record, None
            except Exception as exc:
                return source_key, source, None, f"{type(exc).__name__}: {exc}"

        def accept(
            source_key: str,
            source,
            record: AnimeRecord | None,
            error: str | None,
        ) -> None:
            if error:
                logging.debug(
                    "Search identity expansion failed for %s: %s",
                    source.name,
                    error,
                )
                return
            if record is None:
                unavailable.add(source_key)
                return
            conflicts = identity.conflicting_ids(record.identity)
            if conflicts:
                logging.warning(
                    "Ignoring conflicting search identity edges from %s: %s",
                    source.name,
                    conflicts,
                )
                return
            records_by_key[source_key] = record
            identity.merge_missing(record.identity)
            titles.extend(record.titles.values())
            titles.extend(record.synonyms)

        first_results = await asyncio.gather(
            *(load(source_key, identity) for source_key in self.source_keys)
        )
        for result in first_results:
            accept(*result)

        before_resolver = identity.fingerprint()
        identity = await self._resolve_identity(identity, _dedupe(titles))
        identity_expanded = (
            identity.fingerprint() != initial_fingerprint
            or identity.fingerprint() != before_resolver
        )

        if identity_expanded and unavailable:
            retry_results = await asyncio.gather(
                *(load(source_key, identity) for source_key in tuple(unavailable))
            )
            for result in retry_results:
                source_key = result[0]
                unavailable.discard(source_key)
                accept(*result)

        return identity, list(records_by_key.values())

    async def enrich_candidate(self, candidate: SearchCandidate) -> SearchCandidate:
        """Best-effort title/ID enrichment for one confirmed search candidate.

        This never treats the same numeric value from two databases as the same
        entity. Other sources are queried only with the candidate's confirmed
        identity graph (plus resolver-confirmed edges), then conflicting records
        are discarded.
        """
        identity, records = await self._records_for_candidate(candidate)
        return _merge_candidate_records(candidate, identity, records)

    async def lookup(
        self,
        external_id: str | int,
        *,
        source_keys: tuple[str, ...] | list[str] | None = None,
    ) -> SearchResultSet:
        value = str(external_id).strip()
        if not value:
            return SearchResultSet(items=[])

        if source_keys is None:
            keys = self.source_keys
        else:
            requested = {str(key).strip().casefold() for key in source_keys}
            keys = tuple(key for key in self.source_keys if key in requested)

        if not keys:
            return SearchResultSet(items=[])

        async def load(source_key: str):
            source = self._source_map[source_key]
            identity = AnimeIdentity.from_mapping({source_key: value})
            try:
                record = await source.get_details(identity)
                return source_key, source, record, None
            except Exception as exc:
                return source_key, source, None, f"{type(exc).__name__}: {exc}"

        loaded = await asyncio.gather(*(load(key) for key in keys))
        candidates: list[SearchCandidate] = []
        errors: dict[str, str] = {}

        for source_key, source, record, error in loaded:
            if error:
                errors[source.name] = error
                continue
            if record is None:
                continue
            # The starting source must confirm the exact source-local ID supplied
            # by the user. Cross-source expansion happens only after this gate.
            if str(record.identity.get(source_key) or "").strip() != value:
                continue
            candidates.append(_candidate_from_record(record))

        if candidates:
            candidates = list(
                await asyncio.gather(
                    *(self.enrich_candidate(candidate) for candidate in candidates)
                )
            )

        return SearchResultSet(
            items=merge_candidates(
                candidates,
                query=value,
                # Direct-ID hits from different databases still merge only by
                # confirmed identity edges, never by number/title coincidence.
                allow_title_merge=False,
            ),
            complete=not errors,
            errors=errors,
        )


def _record_year(record: AnimeRecord) -> int | None:
    if record.season_year is not None:
        return record.season_year
    return record.aired_on.year if record.aired_on is not None else None


def _merge_candidate_records(
    candidate: SearchCandidate,
    identity: AnimeIdentity,
    records: list[AnimeRecord],
) -> SearchCandidate:
    aliases = [*candidate.aliases]
    posters = [*candidate.posters]
    scores = dict(candidate.scores)
    romaji_title = candidate.romaji_title
    year = candidate.year

    for record in records:
        aliases.extend(record.titles.values())
        aliases.extend(record.synonyms)
        posters.extend(record.posters)
        if romaji_title is None and record.titles.get("romaji"):
            romaji_title = record.titles["romaji"]
        if year is None:
            year = _record_year(record)
        if record.score is not None:
            scores[record.source] = record.score

    aliases = [
        value
        for value in _dedupe(aliases)
        if value.casefold() != candidate.title.casefold()
    ]
    return SearchCandidate(
        title=candidate.title,
        aliases=aliases,
        year=year,
        external_ids=dict(identity.external_ids),
        scores=scores,
        romaji_title=romaji_title,
        posters=_dedupe(posters),
    )


def _candidate_from_record(record: AnimeRecord) -> SearchCandidate:
    title_order = ("russian", "english", "romaji", "japanese", "native")
    title = next(
        (record.titles[key] for key in title_order if record.titles.get(key)),
        next(iter(record.titles.values()), "Без названия"),
    )

    aliases = [
        value
        for value in _dedupe([*record.titles.values(), *record.synonyms])
        if value.casefold() != title.casefold()
    ]

    scores: dict[str, float] = {}
    if record.score is not None:
        scores[record.source] = record.score

    return SearchCandidate(
        title=title,
        aliases=aliases,
        year=_record_year(record),
        external_ids=dict(record.identity.external_ids),
        scores=scores,
        romaji_title=record.titles.get("romaji"),
        posters=list(record.posters),
    )


def _dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result