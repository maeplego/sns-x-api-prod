import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.database import get_db
from app.core.models import User
from app.request.auth import get_current_user
from app.request.feed.blender import insert_who_to_follow
from app.request.feed.pipeline import build_feed_pipeline, build_following_pipeline
from app.request.feed.schemas import (
    FeedItem,
    FeedPostItem,
    FeedResponse,
    WhoToFollowModuleItem,
    WhoToFollowResponse,
)
from app.request.feed.types import FeedCandidate, FeedQuery, decode_cursor
from app.request.feed.who_to_follow import fetch_who_to_follow
from app.request.side_effects.feed_impression import record_feed_impressions

router = APIRouter(tags=["feed"])
for_you_pipeline = build_feed_pipeline()
following_pipeline = build_following_pipeline()


async def _run_feed_impression_side_effect(viewer_id: uuid.UUID, post_ids: list[uuid.UUID]) -> None:
    async with database.SessionLocal() as db:
        await record_feed_impressions(db, viewer_id, post_ids)


def _parse_cursor(cursor: str | None) -> tuple | None:
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc


def _post_items(candidates: list[FeedCandidate]) -> list[FeedPostItem]:
    return [
        FeedPostItem(
            id=c.id,
            author_id=c.author_id,
            author_handle=c.author_handle or "unknown",
            author_display_name=c.author_display_name or "Unknown",
            body=c.body,
            created_at=c.created_at,
            rank_score=c.rank_score,
            parent_id=c.parent_id,
        )
        for c in candidates
    ]


def _post_ids(items: list[FeedItem]) -> list[uuid.UUID]:
    return [item.id for item in items if item.kind == "post"]


async def _blend_who_to_follow(
    db: AsyncSession,
    viewer_id: uuid.UUID,
    cursor: str | None,
    items: list[FeedPostItem],
) -> list[FeedItem]:
    if cursor is not None:
        return items
    users = await fetch_who_to_follow(db, viewer_id)
    if not users:
        return items
    return insert_who_to_follow(items, WhoToFollowModuleItem(users=users))


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    background_tasks: BackgroundTasks,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    query = FeedQuery(viewer_id=current_user.id, cursor=_parse_cursor(cursor), limit=limit)
    candidates, next_cursor = await for_you_pipeline.run(db, query)
    items = await _blend_who_to_follow(db, current_user.id, cursor, _post_items(candidates))
    response = FeedResponse(items=items, next_cursor=next_cursor, surface="for_you")
    background_tasks.add_task(
        _run_feed_impression_side_effect,
        current_user.id,
        _post_ids(response.items),
    )
    return response


@router.get("/feed/following", response_model=FeedResponse)
async def get_following_feed(
    background_tasks: BackgroundTasks,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    query = FeedQuery(viewer_id=current_user.id, cursor=_parse_cursor(cursor), limit=limit)
    candidates, next_cursor = await following_pipeline.run(db, query)
    items = await _blend_who_to_follow(db, current_user.id, cursor, _post_items(candidates))
    response = FeedResponse(items=items, next_cursor=next_cursor, surface="following")
    background_tasks.add_task(
        _run_feed_impression_side_effect,
        current_user.id,
        _post_ids(response.items),
    )
    return response


@router.get("/who-to-follow", response_model=WhoToFollowResponse)
async def get_who_to_follow(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhoToFollowResponse:
    users = await fetch_who_to_follow(db, current_user.id)
    return WhoToFollowResponse(users=users)
