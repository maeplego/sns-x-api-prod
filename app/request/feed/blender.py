from typing import TypeVar

from app.request.feed.types import FeedCandidate, FeedQuery

T = TypeVar("T")

# 1-indexed slot, matching home-mixer WHO_TO_FOLLOW_POSITION.
WHO_TO_FOLLOW_POSITION = 6


class SourceBlender:
    """Merge Thunder (in-network) and OutOfNetwork candidates with dedup and quota."""

    def __init__(self, oon_ratio: float = 0.3) -> None:
        self.oon_ratio = oon_ratio

    def blend(self, query: FeedQuery, batches: dict[str, list[FeedCandidate]]) -> list[FeedCandidate]:
        thunder = batches.get("thunder", [])
        oon = batches.get("oon", [])

        seen_ids: set = set()
        merged: list[FeedCandidate] = []

        for candidate in thunder:
            if candidate.id in seen_ids:
                continue
            seen_ids.add(candidate.id)
            candidate.source = "thunder"
            merged.append(candidate)

        oon_cap = max(1, int(query.limit * self.oon_ratio))
        oon_added = 0
        for candidate in oon:
            if candidate.id in seen_ids:
                continue
            if oon_added >= oon_cap:
                break
            seen_ids.add(candidate.id)
            candidate.source = "oon"
            merged.append(candidate)
            oon_added += 1

        return merged


def insert_who_to_follow(items: list[T], module: T) -> list[T]:
    """Insert a non-post module at a fixed slot (Blending Pipeline).

    SourceBlender merges post sources. This function is the next stage:
    ranked posts stay in order, Who to Follow is spliced in at position 6
    (or at the end when the page is shorter).
    """
    result = list(items)
    insert_idx = min(WHO_TO_FOLLOW_POSITION - 1, len(result))
    result.insert(insert_idx, module)
    return result
