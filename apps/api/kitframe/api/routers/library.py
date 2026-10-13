from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.auth.permissions import brand_role_allows
from kitframe.db.models import GoldenSetImage, ModelReferenceSet, ReferenceImage, RightsRecord
from kitframe.errors import AppError, ErrorCode
from kitframe.jobs.enqueue import enqueue_job
from kitframe.media.storage import presign_get

router = APIRouter(tags=["library"])


class SetCreate(BaseModel):
    name: str
    kind: str
    rights_record_id: UUID | None = None
    notes: str = ""


class SetPatch(BaseModel):
    name: str | None = None
    notes: str | None = None
    status: str | None = None


class ImageCreate(BaseModel):
    storage_key: str
    name: str = ""
    tags: list[str] = Field(default_factory=list)
    kind: str | None = None


class GoldenCreate(BaseModel):
    garment_category: str
    shot_type: str
    storage_key: str


class GoldenPatch(BaseModel):
    crest_bbox: dict[str, Any] | None = None


@router.get("/reference-sets")
async def list_sets(
    ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep, status: str = "active"
) -> dict[str, Any]:
    q = select(ModelReferenceSet).where(ModelReferenceSet.brand_id == ctx.brand_id)
    if status:
        q = q.where(ModelReferenceSet.status == status)
    rows = (await session.execute(q)).scalars().all()
    data = []
    for s in rows:
        imgs = (
            await session.execute(
                select(ReferenceImage)
                .where(ReferenceImage.set_id == s.id)
                .order_by(ReferenceImage.sort_order, ReferenceImage.created_at)
            )
        ).scalars().all()
        rights_status = None
        if s.rights_record_id:
            rec = await session.get(RightsRecord, s.rights_record_id)
            rights_status = rec.status if rec else None
        cover_url = None
        if imgs:
            try:
                cover_url = presign_get(settings, imgs[0].storage_key)
            except Exception:
                cover_url = None
        data.append(
            {
                **_ser_set(s),
                "photo_count": len(imgs),
                "cover_url": cover_url,
                "rights_status": rights_status,
                "usable": s.kind == "synthetic" or rights_status == "cleared",
            }
        )
    return {"data": data}


@router.post("/reference-sets")
async def create_set(body: SetCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "library.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    if body.kind == "real_person" and body.rights_record_id is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "rights_record_id required", status_code=422)
    s = ModelReferenceSet(brand_id=ctx.brand_id, name=body.name, kind=body.kind, rights_record_id=body.rights_record_id, notes=body.notes, created_by=ctx.user.id)
    session.add(s)
    await session.commit()
    return _ser_set(s)


@router.get("/reference-sets/{set_id}")
async def get_set(
    set_id: UUID, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    s = await session.get(ModelReferenceSet, set_id)
    if s is None or s.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    imgs = (await session.execute(select(ReferenceImage).where(ReferenceImage.set_id == s.id))).scalars().all()
    return {**_ser_set(s), "images": [_ser_img(i, settings) for i in imgs]}


@router.patch("/reference-sets/{set_id}")
async def patch_set(set_id: UUID, body: SetPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "library.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    s = await session.get(ModelReferenceSet, set_id)
    if s is None or s.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await session.commit()
    return _ser_set(s)


@router.post("/reference-sets/{set_id}/images")
async def add_set_image(set_id: UUID, body: ImageCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "library.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    s = await session.get(ModelReferenceSet, set_id)
    if s is None or s.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    img = ReferenceImage(brand_id=ctx.brand_id, kind="model", set_id=set_id, name=body.name, tags=body.tags, storage_key=body.storage_key, sha256="pending", created_by=ctx.user.id)
    session.add(img)
    await session.flush()
    await enqueue_job(session, brand_id=ctx.brand_id, type="validate_reference_image", entity_type="reference_image", entity_id=img.id, requested_by=ctx.user.id)
    await session.commit()
    return _ser_img(img)


@router.get("/reference-images")
async def list_images(
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
    kind: str = Query(...),
    tag: str | None = None,
) -> dict[str, Any]:
    q = select(ReferenceImage).where(ReferenceImage.brand_id == ctx.brand_id, ReferenceImage.kind == kind)
    rows = (await session.execute(q)).scalars().all()
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    return {"data": [_ser_img(r, settings) for r in rows]}


@router.post("/reference-images")
async def create_image(body: ImageCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "library.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    kind = body.kind or "pose"
    if kind not in ("pose", "style"):
        raise AppError(ErrorCode.VALIDATION_ERROR, "kind must be pose|style", status_code=422)
    img = ReferenceImage(brand_id=ctx.brand_id, kind=kind, name=body.name, tags=body.tags, storage_key=body.storage_key, sha256="pending", created_by=ctx.user.id)
    session.add(img)
    await session.flush()
    await enqueue_job(session, brand_id=ctx.brand_id, type="validate_reference_image", entity_type="reference_image", entity_id=img.id, requested_by=ctx.user.id)
    await session.commit()
    return _ser_img(img)


@router.patch("/reference-images/{image_id}")
async def patch_image(image_id: UUID, body: ImageCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "library.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    img = await session.get(ReferenceImage, image_id)
    if img is None or img.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    if body.name:
        img.name = body.name
    if body.tags is not None:
        img.tags = body.tags
    await session.commit()
    return _ser_img(img)


@router.delete("/reference-images/{image_id}", status_code=204)
async def delete_image(image_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> None:
    if not brand_role_allows(ctx.membership.role, "library.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    img = await session.get(ReferenceImage, image_id)
    if img is None or img.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    await session.delete(img)
    await session.commit()


@router.get("/golden-set")
async def list_golden(ctx: BrandAuthDep, session: SessionDep, garment_category: str | None = None, status: str | None = None) -> dict[str, Any]:
    q = select(GoldenSetImage).where(GoldenSetImage.brand_id == ctx.brand_id)
    if garment_category:
        q = q.where(GoldenSetImage.garment_category == garment_category)
    if status:
        q = q.where(GoldenSetImage.status == status)
    rows = (await session.execute(q)).scalars().all()
    return {"data": [_ser_golden(g) for g in rows]}


@router.post("/golden-set")
async def create_golden(body: GoldenCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "golden.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    g = GoldenSetImage(brand_id=ctx.brand_id, garment_category=body.garment_category, shot_type=body.shot_type, storage_key=body.storage_key, created_by=ctx.user.id)
    session.add(g)
    await session.commit()
    return _ser_golden(g)


@router.patch("/golden-set/{golden_id}")
async def patch_golden(golden_id: UUID, body: GoldenPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "golden.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    g = await session.get(GoldenSetImage, golden_id)
    if g is None or g.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    if g.status != "draft":
        raise AppError(ErrorCode.CONFLICT, "Only drafts editable", status_code=409)
    if body.crest_bbox is not None:
        g.crest_bbox = body.crest_bbox
    await session.commit()
    return _ser_golden(g)


@router.post("/golden-set/{golden_id}/approve")
async def approve_golden(golden_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    from kitframe.auth.permissions import can
    if not await can(session, ctx, "golden.approve"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    g = await session.get(GoldenSetImage, golden_id)
    if g is None or g.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    prev = (
        await session.execute(
            select(GoldenSetImage).where(
                GoldenSetImage.brand_id == ctx.brand_id,
                GoldenSetImage.garment_category == g.garment_category,
                GoldenSetImage.shot_type == g.shot_type,
                GoldenSetImage.status == "approved",
            )
        )
    ).scalar_one_or_none()
    if prev and prev.id != g.id:
        prev.status = "archived"
        g.supersedes_id = prev.id
    g.status = "approved"
    g.approved_by = ctx.user.id
    g.approved_at = datetime.now(UTC)
    await session.commit()
    return _ser_golden(g)


@router.post("/golden-set/{golden_id}/archive")
async def archive_golden(golden_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "golden.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    g = await session.get(GoldenSetImage, golden_id)
    if g is None or g.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    g.status = "archived"
    await session.commit()
    return _ser_golden(g)


def _ser_set(s: ModelReferenceSet) -> dict[str, Any]:
    return {"id": str(s.id), "name": s.name, "kind": s.kind, "rights_record_id": str(s.rights_record_id) if s.rights_record_id else None, "status": s.status, "notes": s.notes}


def _ser_img(i: ReferenceImage, settings: SettingsDep | None = None) -> dict[str, Any]:
    url = None
    if settings is not None:
        try:
            url = presign_get(settings, i.storage_key)
        except Exception:
            url = None
    return {
        "id": str(i.id),
        "kind": i.kind,
        "set_id": str(i.set_id) if i.set_id else None,
        "name": i.name,
        "tags": i.tags,
        "storage_key": i.storage_key,
        "url": url,
        "validation_status": i.validation_status,
        "width": i.width,
        "height": i.height,
        "sort_order": i.sort_order,
    }


def _ser_golden(g: GoldenSetImage) -> dict[str, Any]:
    return {"id": str(g.id), "garment_category": g.garment_category, "shot_type": g.shot_type, "storage_key": g.storage_key, "crest_bbox": g.crest_bbox, "status": g.status, "reference_colors": g.reference_colors}
