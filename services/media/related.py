from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.capabilities import SourceCapability
from core.identity import AnimeIdentity
from core.related_anime import (
    AggregatedAnimeReference,
    AnimeReference,
    RELATION_ORDER,
    canonical_relation_kind,
)
from sources.runtime.catalog import source_supports


class IdentityMappingResolver(Protocol):
    def enrich(self, identity: AnimeIdentity) -> AnimeIdentity: ...


@dataclass(slots=True)
class RelatedAnimeLoadResult:
    items: list[AggregatedAnimeReference] = field(default_factory=list)
    by_source: dict[str, list[AggregatedAnimeReference]] = field(default_factory=dict)
    source_names: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _sort_items(
    items: list[AggregatedAnimeReference], *, recommendations: bool
) -> None:
    if recommendations:
        items.sort(
            key=lambda item: (
                -len(item.sources),
                -item.rank_score,
                item.candidate.title.casefold(),
            )
        )
        return
    items.sort(
        key=lambda item: (
            min(
                (RELATION_ORDER.get(value, 99) for value in item.relations),
                default=99,
            ),
            -len(item.sources),
            -item.rank_score,
            item.candidate.title.casefold(),
        )
    )


def _borrow_display_metadata(
    target: AggregatedAnimeReference,
    aggregate: AggregatedAnimeReference,
) -> None:
    for key, value in aggregate.titles.items():
        target.titles.setdefault(key, value)
    target.aliases = _dedupe([*target.aliases, *aggregate.aliases])
    target.posters = _dedupe([*target.posters, *aggregate.posters])


class RelatedAnimeService:
    """Aggregate lazy related/recommended titles without choosing a canonical DB."""

    def __init__(
        self,
        sources: tuple[Any, ...] | list[Any],
        mapping_resolver: IdentityMappingResolver,
    ) -> None:
        self._sources = tuple(sources)
        self._mapping_resolver = mapping_resolver

    async def load_relations(self, identity: AnimeIdentity) -> RelatedAnimeLoadResult:
        return await self._load(
            identity,
            loader_name="load_relations",
            capability=SourceCapability.RELATIONS,
            recommendations=False,
        )

    async def load_recommendations(
        self, identity: AnimeIdentity
    ) -> RelatedAnimeLoadResult:
        return await self._load(
            identity,
            loader_name="load_recommendations",
            capability=SourceCapability.RECOMMENDATIONS,
            recommendations=True,
        )

    async def _load(
        self,
        identity: AnimeIdentity,
        *,
        loader_name: str,
        capability: SourceCapability,
        recommendations: bool,
    ) -> RelatedAnimeLoadResult:
        capable: list[Any] = []
        for source in self._sources:
            source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
            loader = getattr(source, loader_name, None)
            if (
                source_key
                and identity.has(source_key)
                and source_supports(source_key, capability)
                and callable(loader)
            ):
                capable.append(source)

        async def run(source: Any):
            source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
            try:
                values = await getattr(source, loader_name)(identity.copy())
                return source.name, source_key, list(values or []), None
            except Exception as exc:
                return (
                    source.name,
                    source_key,
                    [],
                    f"{type(exc).__name__}: {exc}",
                )

        result = RelatedAnimeLoadResult()
        if not capable:
            return result

        loaded = await asyncio.gather(*(run(source) for source in capable))
        merged: list[AggregatedAnimeReference] = []
        for source_name, source_key, values, error in loaded:
            if error:
                result.errors[source_name] = error
                continue

            local_items: list[AggregatedAnimeReference] = []
            for reference in values[:30]:
                if (
                    not isinstance(reference, AnimeReference)
                    or reference.identity.is_empty()
                ):
                    continue
                enriched = self._mapping_resolver.enrich(reference.identity)
                if enriched.matches(identity):
                    continue
                self._merge_reference(local_items, reference, enriched)
                self._merge_reference(merged, reference, enriched)

            if local_items:
                _sort_items(local_items, recommendations=recommendations)
                result.by_source[source_key] = local_items
                result.source_names[source_key] = next(
                    (
                        value.source
                        for value in values
                        if isinstance(value, AnimeReference) and value.source.strip()
                    ),
                    source_name,
                )

        _sort_items(merged, recommendations=recommendations)
        result.items = merged

        # Keep source-local semantics (its own relation type and ordering), but
        # reuse richer title/poster metadata from the confirmed cross-source peer.
        for local_items in result.by_source.values():
            for local_item in local_items:
                aggregate = next(
                    (
                        item
                        for item in merged
                        if item.identity.matches(local_item.identity)
                    ),
                    None,
                )
                if aggregate is not None:
                    _borrow_display_metadata(local_item, aggregate)
        return result

    @staticmethod
    def _merge_reference(
        merged: list[AggregatedAnimeReference],
        reference: AnimeReference,
        identity: AnimeIdentity,
    ) -> None:
        matching = [
            index
            for index, item in enumerate(merged)
            if item.identity.matches(identity)
        ]
        if matching:
            target = merged[matching[0]]
            for index in reversed(matching[1:]):
                other = merged[index]
                if not target.identity.conflicting_ids(other.identity):
                    RelatedAnimeService._merge_aggregated(target, other)
                    del merged[index]
        else:
            target = AggregatedAnimeReference()
            merged.append(target)

        current_identity = target.identity
        if current_identity.conflicting_ids(identity):
            return
        target.external_ids.update(identity.external_ids)
        for key, raw_value in reference.titles.items():
            value = " ".join(str(raw_value or "").split()).strip()
            if not value:
                continue
            existing = target.titles.get(key)
            if existing is None:
                target.titles[key] = value
            elif existing.casefold() != value.casefold():
                target.aliases = _dedupe([*target.aliases, value])
        target.aliases = _dedupe([*target.aliases, *reference.aliases])
        target.posters = _dedupe([*target.posters, *reference.posters])
        target.sources = _dedupe([*target.sources, reference.source])
        if reference.relation:
            relation = canonical_relation_kind(reference.relation)
            target.relations = _dedupe([*target.relations, relation])
        target.rank_score += 1.0 / max(1, int(reference.rank))

    @staticmethod
    def _merge_aggregated(
        target: AggregatedAnimeReference,
        other: AggregatedAnimeReference,
    ) -> None:
        target.external_ids.update(other.external_ids)
        for key, value in other.titles.items():
            existing = target.titles.get(key)
            if existing is None:
                target.titles[key] = value
            elif existing.casefold() != value.casefold():
                target.aliases = _dedupe([*target.aliases, value])
        target.aliases = _dedupe([*target.aliases, *other.aliases])
        target.posters = _dedupe([*target.posters, *other.posters])
        target.relations = _dedupe([*target.relations, *other.relations])
        target.sources = _dedupe([*target.sources, *other.sources])
        target.rank_score += other.rank_score
