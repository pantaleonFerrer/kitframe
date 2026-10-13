from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep
from kitframe.auth.permissions import brand_role_allows
from kitframe.db.models import RightsRecord
from kitframe.errors import AppError, ErrorCode

router = APIRouter(tags=["rights"])


class RightsIn(BaseModel):
    subject_type: str
    subject_name: str
    aliases: list[str] = Field(default_factory=list)
    status: str = "not_cleared"
    valid_until: date | None = None
    notes: str = ""


class RightsPatch(BaseModel):
    subject_type: str | None = None
    subject_name: str | None = None
    aliases: list[str] | None = None
    status: str | None = None
    valid_until: date | None = None
    notes: str | None = None


@router.get("/rights-records")
async def list_rights(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "rights.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    rows = (await session.execute(select(RightsRecord).where(RightsRecord.brand_id == ctx.brand_id).order_by(RightsRecord.subject_name))).scalars().all()
    return {"data": [_ser(r) for r in rows]}


@router.post("/rights-records")
async def create_rights(body: RightsIn, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "rights.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    r = RightsRecord(brand_id=ctx.brand_id, **body.model_dump())
    if body.status == "cleared":
        if len(body.notes) < 10:
            raise AppError(ErrorCode.VALIDATION_ERROR, "notes required when clearing", status_code=422)
        r.cleared_at = datetime.now(UTC)
        r.cleared_by = ctx.user.id
    session.add(r)
    await session.commit()
    return _ser(r)


@router.patch("/rights-records/{record_id}")
async def patch_rights(record_id: UUID, body: RightsPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "rights.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    r = await session.get(RightsRecord, record_id)
    if r is None or r.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    data = body.model_dump(exclude_unset=True)
    if data.get("status") == "cleared":
        notes = data.get("notes", r.notes)
        if len(notes or "") < 10:
            raise AppError(ErrorCode.VALIDATION_ERROR, "notes >= 10 required", status_code=422)
        r.cleared_at = datetime.now(UTC)
        r.cleared_by = ctx.user.id
    for k, v in data.items():
        setattr(r, k, v)
    r.updated_at = datetime.now(UTC)
    await session.commit()
    return _ser(r)


def _ser(r: RightsRecord) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "subject_type": r.subject_type,
        "subject_name": r.subject_name,
        "aliases": r.aliases,
        "status": r.status,
        "valid_until": r.valid_until.isoformat() if r.valid_until else None,
        "notes": r.notes,
        "cleared_at": r.cleared_at.isoformat() if r.cleared_at else None,
    }
