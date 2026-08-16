import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Report, User
from app.request.audit import write_audit_event
from app.request.auth import get_current_user
from app.request.deps import require_permissions
from app.request.schemas import ReportCreateRequest, ReportResolveRequest, ReportResponse

router = APIRouter(tags=["reports"])


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Report:
    report = Report(
        reporter_id=current_user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        status="open",
    )
    db.add(report)
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="report.create",
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(report)
    return report


@router.get("/moderation/reports", response_model=list[ReportResponse])
async def list_reports(
    status_filter: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_permissions("report.read")),
    db: AsyncSession = Depends(get_db),
) -> list[Report]:
    stmt = select(Report).order_by(Report.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Report.status == status_filter)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.patch("/moderation/reports/{report_id}", response_model=ReportResponse)
async def resolve_report(
    report_id: uuid.UUID,
    body: ReportResolveRequest,
    request: Request,
    current_user: User = Depends(require_permissions("report.resolve")),
    db: AsyncSession = Depends(get_db),
) -> Report:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    report.status = body.status
    report.resolved_at = datetime.now(UTC)
    report.resolver_id = current_user.id
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="report.resolve",
        target_type="report",
        target_id=report.id,
        reason=body.reason or "",
        ip=request.client.host if request.client else None,
        metadata={"status": body.status},
    )
    await db.commit()
    await db.refresh(report)
    return report
