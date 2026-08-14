import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.database import get_db
from app.core.models import User
from app.request.auth import get_current_user
from app.request.feed.pipeline import build_feed_pipeline
from app.request.feed.schemas import FeedPostItem, FeedResponse
from app.request.feed.types import FeedQuery, decode_cursor
from app.request.side_effects.feed_impression import record_feed_impressions

router = APIRouter(tags=["feed"])
pipeline = build_feed_pipeline()


async def _run_feed_impression_side_effect(viewer_id: uuid.UUID, post_ids: list[uuid.UUID]) -> None:
    async with database.SessionLocal() as db:
        await record_feed_impressions(db, viewer_id, post_ids)


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    background_tasks: BackgroundTasks,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    parsed_cursor = None
    if cursor is not None:
        try:
            parsed_cursor = decode_cursor(cursor)
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor",
            ) from exc

    query = FeedQuery(viewer_id=current_user.id, cursor=parsed_cursor, limit=limit)
    candidates, next_cursor = await pipeline.run(db, query)

    items = [
        FeedPostItem(
            id=c.id,
            author_id=c.author_id,
            author_handle=c.author_handle or "unknown",
            author_display_name=c.author_display_name or "Unknown",
            body=c.body,
            created_at=c.created_at,
            rank_score=c.rank_score,
        )
        for c in candidates
    ]

    background_tasks.add_task(
        _run_feed_impression_side_effect,
        current_user.id,
        [item.id for item in items],
    )

    return FeedResponse(items=items, next_cursor=next_cursor)
