from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.auth.permissions import brand_role_allows, can
from kitframe.db.models import Asset, AssetVersion, Product, QCOverride, QCRun
from kitframe.errors import AppError, ErrorCode
from kitframe.jobs.enqueue import enqueue_job
from kitframe.media.storage import presign_get
from kitframe.studio.assignments import complete_open_assignments, user_has_open_assignment
from kitframe.studio.reviews import open_thread_review
from kitframe.workflow import transitions

router = APIRouter(tags=["assets"])


class AssetCreate(BaseModel):
    storage_key: str
    shot_type: str


class AssetPatch(BaseModel):
    status: str | None = None
    shot_type: str | None = None
    sort_order: int | None = None
    alt_text: dict[str, Any] | None = None


class VersionCreate(BaseModel):
    storage_key: str


class CurrentVersionBody(BaseModel):
    version_id: UUID


class OverrideBody(BaseModel):
    reason: str = Field(min_length=10)


@router.get("/products/{product_id}/assets")
async def list_assets(
    product_id: UUID,
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
    status: str | None = None,
) -> dict[str, Any]:
    await _product(session, ctx.brand_id, product_id)
    q = select(Asset).where(Asset.product_id == product_id).order_by(Asset.sort_order)
    if status:
        q = q.where(Asset.status == status)
    rows = (await session.execute(q)).scalars().all()
    return {"data": [await _ser_asset(session, a, settings) for a in rows]}


@router.post("/products/{product_id}/assets")
async def create_asset(product_id: UUID, body: AssetCreate, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    product = await _product(session, ctx.brand_id, product_id)
    if not await can(session, ctx, "product.edit_assets", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    if product.current_phase not in ("visuals", "retouch"):
        raise AppError(ErrorCode.PHASE_LOCKED, "Assets not editable", status_code=409)
    phase = await transitions.get_phase(session, product.id, product.current_phase)
    transitions.assert_not_locked(phase)
    asset = Asset(
        brand_id=ctx.brand_id,
        product_id=product_id,
        shot_type=body.shot_type,
        origin="real_photo",
        status="candidate",
        created_by=ctx.user.id,
    )
    session.add(asset)
    await session.flush()
    open_r = await open_thread_review(session, product)
    # Placeholder dimensions until worker validates
    version = AssetVersion(
        asset_id=asset.id,
        version_number=1,
        source="upload",
        storage_key=body.storage_key,
        mime_type="image/jpeg",
        width=2048,
        height=2048,
        sha256="pending",
        created_by=ctx.user.id,
        review_id=open_r.id if open_r else None,
    )
    session.add(version)
    await session.flush()
    asset.current_version_id = version.id
    await enqueue_job(session, brand_id=ctx.brand_id, type="run_qc", entity_type="asset_version", entity_id=version.id, requested_by=ctx.user.id)
    await session.commit()
    return await _ser_asset(session, asset)


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: UUID, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    asset = await _asset(session, ctx.brand_id, asset_id)
    data = await _ser_asset(session, asset)
    versions = (await session.execute(select(AssetVersion).where(AssetVersion.asset_id == asset.id).order_by(AssetVersion.version_number.desc()))).scalars().all()
    data["versions"] = []
    for v in versions:
        run = (
            await session.execute(
                select(QCRun).where(QCRun.asset_version_id == v.id).order_by(QCRun.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        override = (
            await session.execute(select(QCOverride).where(QCOverride.asset_version_id == v.id).limit(1))
        ).scalar_one_or_none()
        data["versions"].append(
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "source": v.source,
                "width": v.width,
                "height": v.height,
                "url": presign_get(settings, v.storage_key),
                "qc": {
                    "result": run.result if run else None,
                    "checks": run.checks if run else None,
                    "override_reason": override.reason if override else None,
                },
            }
        )
    return data


@router.patch("/assets/{asset_id}")
async def patch_asset(asset_id: UUID, body: AssetPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    asset = await _asset(session, ctx.brand_id, asset_id)
    product = await session.get(Product, asset.product_id)
    if not await can(session, ctx, "product.edit_assets", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    data = body.model_dump(exclude_unset=True)
    becoming_selected = data.get("status") == "selected" and asset.status != "selected"
    if "alt_text" in data and data["alt_text"] is not None:
        alt = dict(data["alt_text"])
        alt["manually_edited"] = True
        data["alt_text"] = alt
    for k, v in data.items():
        setattr(asset, k, v)
    if becoming_selected and not (asset.alt_text or {}).get("es"):
        await enqueue_job(
            session,
            brand_id=ctx.brand_id,
            type="generate_alt_text",
            entity_type="asset",
            entity_id=asset.id,
            requested_by=ctx.user.id,
        )
    await session.commit()
    return await _ser_asset(session, asset)


@router.post("/assets/{asset_id}/versions")
async def add_version(asset_id: UUID, body: VersionCreate, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    asset = await _asset(session, ctx.brand_id, asset_id)
    product = await session.get(Product, asset.product_id)
    can_edit = await can(session, ctx, "product.edit_assets", product=product)
    has_assignment = await user_has_open_assignment(
        session, asset_id=asset.id, user_id=ctx.user.id
    )
    if not can_edit and not has_assignment:
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    if product is not None and can_edit and not has_assignment:
        phase = await transitions.get_phase(session, product.id, product.current_phase)
        transitions.assert_not_locked(phase)
    count = len((await session.execute(select(AssetVersion).where(AssetVersion.asset_id == asset.id))).scalars().all())
    open_r = await open_thread_review(session, product) if product is not None else None
    version = AssetVersion(
        asset_id=asset.id,
        version_number=count + 1,
        source="upload",
        storage_key=body.storage_key,
        mime_type="image/jpeg",
        width=2048,
        height=2048,
        sha256="pending",
        created_by=ctx.user.id,
        review_id=open_r.id if open_r else None,
    )
    session.add(version)
    await session.flush()
    asset.current_version_id = version.id
    if has_assignment:
        await complete_open_assignments(
            session, asset_id=asset.id, user_id=ctx.user.id, version_id=version.id
        )
    await enqueue_job(session, brand_id=ctx.brand_id, type="run_qc", entity_type="asset_version", entity_id=version.id, requested_by=ctx.user.id)
    await session.commit()
    return {"version_id": str(version.id)}


@router.post("/assets/{asset_id}/current-version")
async def set_current(asset_id: UUID, body: CurrentVersionBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    asset = await _asset(session, ctx.brand_id, asset_id)
    product = await session.get(Product, asset.product_id)
    if not await can(session, ctx, "product.edit_assets", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    version = await session.get(AssetVersion, body.version_id)
    if version is None or version.asset_id != asset.id:
        raise AppError(ErrorCode.NOT_FOUND, "Version not found", status_code=404)
    asset.current_version_id = version.id
    await session.commit()
    return {"current_version_id": str(version.id)}


@router.post("/assets/{asset_id}/remove-background")
async def remove_bg(asset_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    asset = await _asset(session, ctx.brand_id, asset_id)
    product = await session.get(Product, asset.product_id)
    if not await can(session, ctx, "product.edit_assets", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    job = await enqueue_job(session, brand_id=ctx.brand_id, type="remove_background", entity_type="asset", entity_id=asset.id, requested_by=ctx.user.id)
    await session.commit()
    return {"job_id": str(job.id)}


@router.post("/asset-versions/{version_id}/qc")
async def run_qc(version_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    version = await session.get(AssetVersion, version_id)
    if version is None:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    asset = await session.get(Asset, version.asset_id)
    if asset is None or asset.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    job = await enqueue_job(session, brand_id=ctx.brand_id, type="run_qc", entity_type="asset_version", entity_id=version.id, requested_by=ctx.user.id)
    await session.commit()
    return {"job_id": str(job.id)}


@router.post("/asset-versions/{version_id}/qc-override")
async def qc_override(version_id: UUID, body: OverrideBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "qc.override"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    version = await session.get(AssetVersion, version_id)
    if version is None:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    asset = await session.get(Asset, version.asset_id)
    if asset is None or asset.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    run = (
        await session.execute(select(QCRun).where(QCRun.asset_version_id == version.id).order_by(QCRun.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    if run is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "No QC run", status_code=422)
    session.add(QCOverride(asset_version_id=version.id, qc_run_id=run.id, user_id=ctx.user.id, reason=body.reason))
    await session.commit()
    return {"status": "ok"}


@router.get("/asset-versions/{version_id}/download")
async def download(version_id: UUID, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep) -> dict[str, str]:
    version = await session.get(AssetVersion, version_id)
    if version is None:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    asset = await session.get(Asset, version.asset_id)
    if asset is None or asset.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    return {"url": presign_get(settings, version.storage_key)}


async def _product(session: SessionDep, brand_id: UUID, product_id: UUID) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.brand_id != brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    return product


async def _asset(session: SessionDep, brand_id: UUID, asset_id: UUID) -> Asset:
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.brand_id != brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    return asset


async def _ser_asset(
    session: SessionDep,
    asset: Asset,
    settings: SettingsDep | None = None,
) -> dict[str, Any]:
    url = None
    if settings is not None and asset.current_version_id:
        version = await session.get(AssetVersion, asset.current_version_id)
        if version is not None:
            try:
                url = presign_get(settings, version.storage_key)
            except Exception:
                url = None
    return {
        "id": str(asset.id),
        "product_id": str(asset.product_id),
        "shot_type": asset.shot_type,
        "origin": asset.origin,
        "status": asset.status,
        "current_version_id": str(asset.current_version_id) if asset.current_version_id else None,
        "url": url,
        "alt_text": asset.alt_text,
        "sort_order": asset.sort_order,
        "generation_id": str(asset.generation_id) if asset.generation_id else None,
    }
