from app.core import database
from app.core.models import Post
from app.core.safety_models import SafetyTargetType
from app.labeling.context import TaskContext
from app.labeling.plan import Task
from app.safety.labels import LABEL_DO_NOT_AMPLIFY, LABEL_NSFW, upsert_label
from app.safety.nsfw import detect_nsfw_text


class ApplyPostSafetyLabelsTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None or not post.body.strip():
                return
            hit = detect_nsfw_text(post.body)
            if hit is None:
                return
            await upsert_label(
                db,
                target_type=SafetyTargetType.POST,
                target_id=post.id,
                label=LABEL_NSFW,
                reason=hit,
            )
            await upsert_label(
                db,
                target_type=SafetyTargetType.POST,
                target_id=post.id,
                label=LABEL_DO_NOT_AMPLIFY,
                reason=f"nsfw:{hit}",
            )
            await db.commit()
