from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.content.ecom_excel import list_rows_to_fill, load_workbook_bytes
from kitframe.db.models import AuditLog, Job
from kitframe.errors import AppError, ErrorCode
from kitframe.jobs.enqueue import enqueue_job
from kitframe.media.storage import presign_get, put_bytes

router = APIRouter(tags=["tools"])

MAX_XLSX = 20 * 1024 * 1024


def _can_fill_ecom(ctx: object) -> bool:
    membership = getattr(ctx, "membership", None)
    role = (membership.role if membership else "") or ""
    return role in ("admin", "owner", "editor")


@router.post("/tools/ecom-descriptions/fill")
async def fill_ecom_descriptions(
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload a 'Descripcions producte per ecom' xlsx; enqueue LLM fill for green rows."""
    if not _can_fill_ecom(ctx):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)

    name = (file.filename or "descripcions.xlsx").strip()
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise AppError(ErrorCode.UPLOAD_INVALID, "Expected an .xlsx file", status_code=422)

    data = await file.read()
    if not data:
        raise AppError(ErrorCode.UPLOAD_INVALID, "Empty file", status_code=422)
    if len(data) > MAX_XLSX:
        raise AppError(ErrorCode.FILE_TOO_LARGE, "File too large", status_code=413)

    try:
        wb = load_workbook_bytes(data)
        pending = list_rows_to_fill(wb)
    except Exception as exc:
        raise AppError(
            ErrorCode.UPLOAD_INVALID,
            f"Could not read workbook: {exc}",
            status_code=422,
        ) from exc

    if not pending:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "No green rows missing Spanish description to fill",
            status_code=422,
        )

    input_key = f"brands/{ctx.brand_id}/ecom_excel/in/{uuid4()}/{name}"
    put_bytes(
        settings,
        input_key,
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    job = await enqueue_job(
        session,
        brand_id=ctx.brand_id,
        type="fill_ecom_excel",
        entity_type="ecom_excel",
        entity_id=None,
        requested_by=ctx.user.id,
        payload={
            "input_storage_key": input_key,
            "original_filename": name,
            "pending_refs": [r.ref for r in pending],
            "pending_count": len(pending),
        },
    )
    session.add(
        AuditLog(
            brand_id=ctx.brand_id,
            user_id=ctx.user.id,
            entity_type="job",
            entity_id=job.id,
            action="fill_ecom_excel",
            detail={"pending_count": len(pending), "filename": name},
            request_id=ctx.request_id,
        )
    )
    await session.commit()
    return {
        "job_id": str(job.id),
        "pending_count": len(pending),
        "pending_refs": [r.ref for r in pending],
    }


@router.get("/tools/ecom-descriptions/jobs/{job_id}")
async def get_ecom_fill_job(
    job_id: Any,
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    from uuid import UUID

    try:
        jid = UUID(str(job_id))
    except ValueError as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid job id", status_code=422) from exc

    if not _can_fill_ecom(ctx):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)

    job = await session.get(Job, jid)
    if job is None or job.brand_id != ctx.brand_id or job.type != "fill_ecom_excel":
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)

    payload = dict(job.payload or {})
    download_url = None
    out_key = payload.get("output_storage_key")
    if job.status == "completed" and out_key:
        download_url = presign_get(settings, str(out_key), expires=3600)

    return {
        "id": str(job.id),
        "status": job.status,
        "error_detail": job.error_detail,
        "pending_count": payload.get("pending_count"),
        "filled_count": payload.get("filled_count"),
        "skipped_count": payload.get("skipped_count"),
        "original_filename": payload.get("original_filename"),
        "download_url": download_url,
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/tools/ecom-descriptions/recent")
async def list_recent_ecom_fills(
    ctx: BrandAuthDep,
    session: SessionDep,
) -> dict[str, Any]:
    if not _can_fill_ecom(ctx):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)

    rows = (
        await session.execute(
            select(Job)
            .where(Job.brand_id == ctx.brand_id, Job.type == "fill_ecom_excel")
            .order_by(Job.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return {
        "data": [
            {
                "id": str(j.id),
                "status": j.status,
                "pending_count": (j.payload or {}).get("pending_count"),
                "filled_count": (j.payload or {}).get("filled_count"),
                "original_filename": (j.payload or {}).get("original_filename"),
                "created_at": j.created_at.isoformat(),
                "error_detail": j.error_detail,
            }
            for j in rows
        ]
    }
