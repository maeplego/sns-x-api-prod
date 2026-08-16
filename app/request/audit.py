import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.middleware import request_id_ctx
from app.core.models import AuditEvent


async def write_audit_event(
    db: AsyncSession,
    *,
    action: str,
    target_type: str,
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    reason: str = "",
    ip: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        ip=ip,
        request_id=request_id_ctx.get(),
        metadata_json=json.dumps(metadata) if metadata is not None else None,
    )
    db.add(event)
    await db.flush()
    return event
