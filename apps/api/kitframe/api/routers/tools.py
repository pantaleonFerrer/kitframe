from __future__ import annotations

import mimetypes
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.content.ecom_excel import (
    is_product_image_filename,
    list_rows_to_fill,
    load_workbook_bytes,
    match_filename_to_ref,
    parse_notes_json,
)
from kitframe.db.models import AuditLog, Job
from kitframe.errors import AppError, ErrorCode
from kitframe.jobs.enqueue import enqueue_job
from kitframe.media.storage import presign_get, put_bytes

router = APIRouter(tags=["tools"])

MAX_XLSX = 20 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_IMAGES_TOTAL = 40


def _can_fill_ecom(ctx: object) -> bool:
    membership = getattr(ctx, "membership", None)
    role = (membership.role if membership else "") or ""
    return role in ("admin", "owner", "editor")


def _guess_image_content_type(filename: str, declared: str | None) -> str:
    if declared and declared.startswith("image/"):
        return declared
    guessed, _ = mimetypes.guess_type(filename)
    if guessed and guessed.startswith("image/"):
        return guessed
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(suffix, "application/octet-stream")


def _job_progress_view(payload: dict[str, Any]) -> dict[str, Any]:
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    return {
        "stage": progress.get("stage") or payload.get("stage"),
        "current": progress.get("current"),
        "total": progress.get("total") or payload.get("pending_count"),
        "current_ref": progress.get("current_ref"),
        "message": progress.get("message"),
        "filled_refs": progress.get("filled_refs") or [],
        "failed_ref": progress.get("failed_ref"),
    }


@router.post("/tools/ecom-descriptions/preview")
async def preview_ecom_descriptions(
    ctx: BrandAuthDep,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Parse workbook and list green rows that still need Spanish copy."""
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

    return {
        "filename": name,
        "pending_count": len(pending),
        "pending": [
            {
                "ref": r.ref,
                "title": r.title,
                "collection": r.collection,
                "product_type": r.product_type,
            }
            for r in pending
        ],
        "image_naming_hint": "Name photos like BLMP813081.jpg or BLMP813081_1.png",
    }


@router.post("/tools/ecom-descriptions/fill")
async def fill_ecom_descriptions(
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    images: Annotated[list[UploadFile], File()] = [],
    image_refs: Annotated[list[str], Form()] = [],
    notes_json: str = Form(default="{}"),
) -> dict[str, Any]:
    """Upload Excel + product photos + notes; enqueue vision LLM fill for green rows.

    Prefer pairing each image with image_refs[i] (UI assigns photos per product).
    Filename matching (BLMP813081.jpg) is a fallback when image_refs is omitted.
    notes_json: {"REF": {"fit":"...","care":"...","measures":"...","extra":"..."}}
    """
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

    try:
        notes = parse_notes_json(notes_json)
    except ValueError as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, str(exc), status_code=422) from exc

    refs = [r.ref for r in pending]
    ref_set = set(refs)
    image_files = [img for img in images if img is not None]
    assigned_refs = [str(r).strip() for r in image_refs if str(r).strip()]
    if len(image_files) > MAX_IMAGES_TOTAL:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Too many images (max {MAX_IMAGES_TOTAL})",
            status_code=422,
        )
    if assigned_refs and len(assigned_refs) != len(image_files):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "image_refs length must match images length",
            status_code=422,
        )

    batch_id = str(uuid4())
    images_by_ref: dict[str, list[dict[str, str]]] = {r: [] for r in refs}
    unmatched: list[str] = []

    for idx, img in enumerate(image_files):
        fname = (img.filename or f"image_{idx}.jpg").strip()
        if not is_product_image_filename(fname) and not (img.content_type or "").startswith("image/"):
            unmatched.append(fname or "(unnamed)")
            continue
        if assigned_refs:
            ref = assigned_refs[idx]
            if ref not in ref_set:
                # case-insensitive fallback
                ref_match = next((r for r in refs if r.upper() == ref.upper()), None)
                if ref_match is None:
                    unmatched.append(fname)
                    continue
                ref = ref_match
        else:
            if not is_product_image_filename(fname):
                unmatched.append(fname)
                continue
            matched = match_filename_to_ref(fname, refs)
            if matched is None:
                unmatched.append(fname)
                continue
            ref = matched

        raw = await img.read()
        if not raw:
            continue
        if len(raw) > MAX_IMAGE:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                f"Image too large: {fname}",
                status_code=413,
            )
        if len(images_by_ref[ref]) >= 8:
            continue
        content_type = _guess_image_content_type(fname, img.content_type)
        # Sanitize filename for storage key (screenshots often have spaces)
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)[:120]
        key = f"brands/{ctx.brand_id}/ecom_excel/in/{batch_id}/images/{ref}/{uuid4().hex}_{safe_name}"
        try:
            put_bytes(settings, key, raw, content_type)
        except Exception as exc:
            raise AppError(
                ErrorCode.PROVIDER_ERROR,
                "Object storage unavailable. Check S3_ENDPOINT / credentials.",
                status_code=503,
                details={"reason": str(exc)[:300]},
            ) from exc
        images_by_ref[ref].append({"storage_key": key, "filename": fname})

    missing_images = [r for r in refs if not images_by_ref[r]]
    if missing_images:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Each product to fill needs at least one photo",
            status_code=422,
            details={
                "missing_images": missing_images,
                "unmatched_images": unmatched,
                "hint": "Attach photos on each product card (filenames like screenshots are fine)",
            },
        )

    input_key = f"brands/{ctx.brand_id}/ecom_excel/in/{batch_id}/{name}"
    try:
        put_bytes(
            settings,
            input_key,
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        raise AppError(
            ErrorCode.PROVIDER_ERROR,
            "Object storage unavailable. Check S3_ENDPOINT / credentials.",
            status_code=503,
            details={"reason": str(exc)[:300]},
        ) from exc

    # Keep only notes for pending refs (case-sensitive keys as in Excel)
    notes_for_job = {r: notes[r] for r in refs if r in notes}
    # Also accept case-insensitive note keys
    notes_lower = {k.upper(): v for k, v in notes.items()}
    for r in refs:
        if r not in notes_for_job and r.upper() in notes_lower:
            notes_for_job[r] = notes_lower[r.upper()]

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
            "pending_refs": refs,
            "pending_count": len(pending),
            "images_by_ref": images_by_ref,
            "notes_by_ref": notes_for_job,
            "unmatched_images": unmatched,
            "progress": {
                "stage": "queued",
                "current": 0,
                "total": len(pending),
                "current_ref": None,
                "message": "Queued",
                "filled_refs": [],
            },
        },
    )
    session.add(
        AuditLog(
            brand_id=ctx.brand_id,
            user_id=ctx.user.id,
            entity_type="job",
            entity_id=job.id,
            action="fill_ecom_excel",
            detail={
                "pending_count": len(pending),
                "filename": name,
                "image_count": sum(len(v) for v in images_by_ref.values()),
            },
            request_id=ctx.request_id,
        )
    )
    await session.commit()
    return {
        "job_id": str(job.id),
        "pending_count": len(pending),
        "pending_refs": refs,
        "images_per_ref": {r: len(images_by_ref[r]) for r in refs},
        "notes_refs": list(notes_for_job.keys()),
        "unmatched_images": unmatched,
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

    progress = _job_progress_view(payload)
    return {
        "id": str(job.id),
        "status": job.status,
        "error_detail": job.error_detail,
        "pending_count": payload.get("pending_count"),
        "filled_count": payload.get("filled_count"),
        "skipped_count": payload.get("skipped_count"),
        "original_filename": payload.get("original_filename"),
        "download_url": download_url,
        "progress": progress,
        "pending_refs": payload.get("pending_refs") or [],
        "images_per_ref": {
            r: len((payload.get("images_by_ref") or {}).get(r) or [])
            for r in (payload.get("pending_refs") or [])
        },
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
                "progress": _job_progress_view(dict(j.payload or {})),
            }
            for j in rows
        ]
    }
