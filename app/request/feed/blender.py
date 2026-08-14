from app.request.feed.types import FeedCandidate, FeedQuery


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
