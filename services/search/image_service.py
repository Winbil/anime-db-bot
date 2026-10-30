from __future__ import annotations

import asyncio

from core.image_search import (
    ImageSearchAvailability,
    ImageSearchCandidate,
    ImageSearchInput,
    ImageSearchMatch,
    ImageSearchQuotaExhausted,
    ImageSearchResultSet,
)
from core.models import SearchCandidate
from services.identity.direct_lookup import DirectIdLookupService


class ImageSearchService:
    """Run scarce screenshot-search providers and resolve matches into anime identities."""

    def __init__(self, providers, direct_lookup: DirectIdLookupService) -> None:
        self.providers = {provider.key: provider for provider in providers}
        if not self.providers:
            raise ValueError("ImageSearchService requires at least one provider")
        self.direct_lookup = direct_lookup

    async def availability(self) -> dict[str, ImageSearchAvailability]:
        async def load(key: str, provider):
            try:
                return key, await provider.availability()
            except Exception:
                return key, ImageSearchAvailability(key, provider.name, True)

        return dict(
            await asyncio.gather(
                *(load(key, provider) for key, provider in self.providers.items())
            )
        )

    async def search(
        self,
        image: ImageSearchInput,
        provider_keys: tuple[str, ...] | list[str],
    ) -> ImageSearchResultSet:
        keys = tuple(
            dict.fromkeys(
                str(key).strip().casefold() for key in provider_keys if str(key).strip()
            )
        )
        selected = [(key, self.providers[key]) for key in keys if key in self.providers]
        if not selected:
            return ImageSearchResultSet(items=[])

        async def run(key: str, provider):
            try:
                return key, provider.name, await provider.search(image), None
            except ImageSearchQuotaExhausted as exc:
                return key, provider.name, [], f"quota: {exc}"
            except Exception as exc:
                return key, provider.name, [], f"{type(exc).__name__}: {exc}"

        loaded = await asyncio.gather(
            *(run(key, provider) for key, provider in selected)
        )
        errors: dict[str, str] = {}
        grouped: dict[str, dict[str, ImageSearchMatch]] = {}
        for _, provider_name, matches, error in loaded:
            if error:
                errors[provider_name] = error
                continue
            for match in matches:
                by_provider = grouped.setdefault(match.anilist_id, {})
                previous = by_provider.get(match.provider_key)
                if previous is None or match.similarity > previous.similarity:
                    by_provider[match.provider_key] = match

        async def resolve(
            anilist_id: str, matches: list[ImageSearchMatch]
        ) -> ImageSearchCandidate:
            best = max(matches, key=lambda item: item.similarity)
            title = (
                best.titles.get("english")
                or best.titles.get("romaji")
                or best.titles.get("native")
                or f"AniList #{anilist_id}"
            )
            aliases = [*best.titles.values(), *best.aliases]
            external_ids = {"anilist": anilist_id}
            if best.mal_id:
                external_ids["mal"] = best.mal_id
            base = SearchCandidate(
                title=title,
                aliases=_dedupe(
                    value
                    for value in aliases
                    if value and value.casefold() != title.casefold()
                ),
                external_ids=external_ids,
                romaji_title=best.titles.get("romaji"),
            )
            try:
                lookup = await self.direct_lookup.lookup(
                    anilist_id,
                    source_keys=("anilist",),
                    enrich_candidates=False,
                )
                candidate = lookup.items[0] if lookup.items else base
            except Exception:
                candidate = base
            if candidate.title.startswith("AniList #") and candidate.aliases:
                preferred_title = candidate.romaji_title or candidate.aliases[0]
                candidate = SearchCandidate(
                    title=preferred_title,
                    aliases=[
                        value
                        for value in candidate.aliases
                        if value.casefold() != preferred_title.casefold()
                    ],
                    year=candidate.year,
                    external_ids=dict(candidate.external_ids),
                    scores=dict(candidate.scores),
                    romaji_title=candidate.romaji_title,
                    posters=list(candidate.posters),
                )
            if not candidate.posters and best.preview_image:
                candidate.posters.append(best.preview_image)
            return ImageSearchCandidate(
                candidate=candidate,
                matches=sorted(
                    matches,
                    key=lambda item: (-item.similarity, item.provider_name.casefold()),
                ),
            )

        resolved = await asyncio.gather(
            *(
                resolve(anilist_id, list(by_provider.values()))
                for anilist_id, by_provider in grouped.items()
            )
        )
        resolved.sort(
            key=lambda item: (
                -max((match.similarity for match in item.matches), default=0.0),
                -len(item.matches),
                item.candidate.title.casefold(),
            )
        )
        return ImageSearchResultSet(items=list(resolved), errors=errors)


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
