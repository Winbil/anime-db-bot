from __future__ import annotations

import asyncio

from core.identity import AnimeIdentity
from core.models import AnimeRecord, SearchCandidate, SearchResultSet
from services.search import merge_candidates


class DirectIdLookupService:
    """Resolve an external ID through identity-native metadata sources."""

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
            # A source is only a direct-ID hit when it confirms the ID that was
            # supplied under that source key. This prevents a resolver/fallback
            # implementation from accidentally accepting a different entity.
            if str(record.identity.get(source_key) or "").strip() != value:
                continue
            candidates.append(_candidate_from_record(record))

        return SearchResultSet(
            items=merge_candidates(
                candidates,
                query=value,
                # Direct-ID results from two databases must not merge merely
                # because their titles happen to match. Only confirmed identity
                # edges returned by the sources are strong enough here.
                allow_title_merge=False,
            ),
            complete=not errors,
            errors=errors,
        )


def _candidate_from_record(record: AnimeRecord) -> SearchCandidate:
    title_order = ("russian", "english", "romaji", "japanese", "native")
    title = next(
        (record.titles[key] for key in title_order if record.titles.get(key)),
        next(iter(record.titles.values()), "Без названия"),
    )

    aliases: list[str] = []
    seen: set[str] = {title.casefold()}
    for value in [*record.titles.values(), *record.synonyms]:
        value = " ".join((value or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            aliases.append(value)

    year = record.season_year
    if year is None:
        aired_on = str(record.aired_on or "")
        if len(aired_on) >= 4 and aired_on[:4].isdigit():
            year = int(aired_on[:4])

    scores: dict[str, float] = {}
    if record.score is not None:
        scores[record.source] = record.score

    return SearchCandidate(
        title=title,
        aliases=aliases,
        year=year,
        external_ids=dict(record.identity.external_ids),
        scores=scores,
        romaji_title=record.titles.get("romaji"),
        posters=list(record.posters),
    )
