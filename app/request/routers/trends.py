"""Hashtag trends — personal-scale time-window aggregation (not x-algorithm Trends)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, PostEngagement, PostStatus
from app.request.auth import get_current_user
from app.request.schemas import TrendItem, TrendsResponse

router = APIRouter(tags=["trends"])

HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_]{2,40})", re.UNICODE)


def extract_hashtags(body: str) -> set[str]:
    return {match.group(1).lower() for match in HASHTAG_RE.finditer(body or "")}


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    window_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=20, ge=1, le=50),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrendsResponse:
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    rows = await db.execute(
        select(Post, PostEngagement)
        .outerjoin(PostEngagement, PostEngagement.post_id == Post.id)
        .where(
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
            Post.created_at >= since,
            Post.body != "",
        )
    )

    stats: dict[str, dict[str, object]] = defaultdict(
        lambda: {"post_count": 0, "like_count": 0, "authors": set()}
    )
    for post, engagement in rows.all():
        tags = extract_hashtags(post.body)
        if not tags:
            continue
        likes = engagement.like_count if engagement is not None else 0
        for tag in tags:
            bucket = stats[tag]
            bucket["post_count"] = int(bucket["post_count"]) + 1
            bucket["like_count"] = int(bucket["like_count"]) + int(likes or 0)
            authors: set = bucket["authors"]  # type: ignore[assignment]
            authors.add(post.author_id)

    ranked: list[TrendItem] = []
    for term, bucket in stats.items():
        authors = bucket["authors"]
        unique_authors = len(authors)  # type: ignore[arg-type]
        post_count = int(bucket["post_count"])
        like_count = int(bucket["like_count"])
        # Prefer multi-author topics over single-user spam floods.
        score = float(unique_authors * 2 + post_count + like_count)
        ranked.append(
            TrendItem(
                term=term,
                score=score,
                post_count=post_count,
                unique_authors=unique_authors,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.term))
    return TrendsResponse(
        window_hours=window_hours,
        items=ranked[:limit],
    )
