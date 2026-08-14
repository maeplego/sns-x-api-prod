import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.social_models import FeedImpression

logger = structlog.get_logger(__name__)


async def record_feed_impressions(
    db: AsyncSession,
    viewer_id: uuid.UUID,
    post_ids: list[uuid.UUID],
) -> None:
    if not post_ids:
        return

    for position, post_id in enumerate(post_ids):
        db.add(
            FeedImpression(
                viewer_id=viewer_id,
                post_id=post_id,
                position=position,
            )
        )
    await db.commit()
    logger.info(
        "feed_impressions_recorded",
        viewer_id=str(viewer_id),
        count=len(post_ids),
    )
