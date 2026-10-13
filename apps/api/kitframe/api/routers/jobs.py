from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep
from kitframe.auth.permissions import brand_role_allows
from kitframe.db.models import AuditLog, Job
from kitframe.errors import AppError, ErrorCode

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    job = await session.get(Job, job_id)
    if job is None or (job.brand_id and job.brand_id != ctx.brand_id):
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    return _ser(job)


@router.get("/jobs")
async def list_jobs(ctx: BrandAuthDep, session: SessionDep, status: str = Query(default="failed")) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.admin"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    rows = (
        await session.execute(
            select(Job).where(Job.brand_id == ctx.brand_id, Job.status == status).order_by(Job.created_at.desc()).limit(100)
        )
    ).scalars().all()
    return {"data": [_ser(j) for j in rows]}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.admin"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    job = await session.get(Job, job_id)
    if job is None or job.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    job.status = "queued"
    job.error_code = None
    job.error_detail = None
    await session.commit()
    return _ser(job)


@router.get("/audit-log")
async def audit_log(ctx: BrandAuthDep, session: SessionDep, entity_type: str | None = None, entity_id: UUID | None = None, user_id: UUID | None = None) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.admin"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    q = select(AuditLog).where(AuditLog.brand_id == ctx.brand_id).order_by(AuditLog.created_at.desc()).limit(200)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    rows = (await session.execute(q)).scalars().all()
    return {
        "data": [
            {
                "id": str(a.id),
                "user_id": str(a.user_id) if a.user_id else None,
                "entity_type": a.entity_type,
                "entity_id": str(a.entity_id),
                "action": a.action,
                "detail": a.detail,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]
    }


def _ser(j: Job) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "type": j.type,
        "status": j.status,
        "entity_type": j.entity_type,
        "entity_id": str(j.entity_id) if j.entity_id else None,
        "attempts": j.attempts,
        "error_code": j.error_code,
        "error_detail": j.error_detail,
        "created_at": j.created_at.isoformat(),
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }
