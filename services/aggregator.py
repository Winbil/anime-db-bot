from __future__ import annotations

import asyncio

from core.contracts import AnimeSource
from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _merge_people(groups: list[list[PersonCredit]]) -> list[PersonCredit]:
    merged: dict[str, PersonCredit] = {}
    for group in groups:
        for person in group:
            key = person.name.casefold()
            current = merged.get(key)
            if current is None:
                merged[key] = PersonCredit(person.name, _dedupe_strings(person.roles))
            else:
                current.roles = _dedupe_strings([*current.roles, *person.roles])
    return list(merged.values())


class AnimeAggregator:
    """Fetch and merge one anime from all metadata sources using one MAL ID."""

    def __init__(self, sources: tuple[AnimeSource, ...] | list[AnimeSource]) -> None:
        self._sources = tuple(sources)

    async def aggregate(self, candidate: SearchCandidate) -> AggregatedAnime:
        mal_id = str(candidate.external_ids.get("mal") or "").strip()
        if not mal_id:
            raise RuntimeError("Search result does not contain a MAL ID")

        async def run(source: AnimeSource):
            try:
                record = await source.get_details(mal_id)
                return source.name, record, None
            except Exception as exc:
                return source.name, None, f"{type(exc).__name__}: {exc}"

        results = await asyncio.gather(*(run(source) for source in self._sources))
        records: list[AnimeRecord] = []
        errors: dict[str, str] = {}

        for source_name, record, error in results:
            if error:
                errors[source_name] = error
            elif record is not None:
                records.append(record)

        if not records:
            raise RuntimeError("No metadata source could provide details for this MAL ID")

        def first(field_name: str):
            for record in records:
                value = getattr(record, field_name)
                if value not in (None, "", [], {}):
                    return value
            return None

        titles: dict[str, str] = {}
        synonyms: list[str] = list(candidate.aliases)
        external_ids = dict(candidate.external_ids)
        scores = dict(candidate.scores)
        descriptions: dict[str, str] = {}
        urls: dict[str, str] = {}

        for record in records:
            for key, value in record.titles.items():
                if value and key not in titles:
                    titles[key] = value
            synonyms.extend(record.synonyms)
            external_ids.update({k: v for k, v in record.external_ids.items() if v})
            if record.score is not None:
                scores[record.source] = record.score
            descriptions.update(record.descriptions)
            urls.update(record.urls)

        title = (
            titles.get("russian")
            or titles.get("romaji")
            or titles.get("english")
            or candidate.title
        )

        return AggregatedAnime(
            title=title,
            titles=titles,
            synonyms=_dedupe_strings(synonyms),
            external_ids=external_ids,
            sources=[record.source for record in records],
            kind=first("kind"),
            status=first("status"),
            rating=first("rating"),
            season=first("season"),
            franchise=first("franchise"),
            episodes_total=first("episodes_total"),
            episodes_aired=first("episodes_aired"),
            duration_minutes=first("duration_minutes"),
            aired_on=first("aired_on"),
            released_on=first("released_on"),
            next_episode_at=first("next_episode_at"),
            scores=scores,
            genres=_dedupe_strings([value for record in records for value in record.genres]),
            studios=_dedupe_strings([value for record in records for value in record.studios]),
            licensors=_dedupe_strings([value for record in records for value in record.licensors]),
            descriptions=descriptions,
            posters=_dedupe_strings([value for record in records for value in record.posters]),
            urls=urls,
            staff=_merge_people([record.staff for record in records]),
            voices=_merge_people([record.voices for record in records]),
            errors=errors,
        )
