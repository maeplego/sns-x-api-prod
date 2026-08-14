import structlog

from app.core import database
from app.core.embedding_models import PostEmbedding
from app.core.models import Post, PostStatus
from app.embedding.encoder import embed_text
from app.labeling.context import TaskContext
from app.labeling.plan import Task

logger = structlog.get_logger(__name__)


class GenerateEmbeddingTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None:
                raise ValueError("post not found")
            if post.status != PostStatus.PUBLISHED:
                raise ValueError("post not published yet")

            vector = embed_text(post.body)
            existing = await db.get(PostEmbedding, post.id)
            if existing is None:
                db.add(PostEmbedding(post_id=post.id, embedding=vector, model="hash-v1"))
            else:
                existing.embedding = vector
                existing.model = "hash-v1"
            await db.commit()
            logger.info("embedding_generated", post_id=str(post.id))
