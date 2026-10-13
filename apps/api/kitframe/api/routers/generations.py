from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.auth.permissions import can
from kitframe.db.models import (
    Asset,
    AssetVersion,
    Brand,
    Generation,
    ModelReferenceSet,
    Product,
    QCRun,
    RateLimitBucket,
    ReferenceImage,
)
from kitframe.errors import AppError, ErrorCode
from kitframe.jobs.enqueue import enqueue_job
from kitframe.providers.registry import get_image_provider
from kitframe.studio.prompt import compose_final_prompt
from kitframe.studio.rights import check_rights

router = APIRouter(tags=["generations"])


class GenerationBody(BaseModel):
    product_id: UUID
    garment_version_ids: list[UUID] = Field(min_length=1, max_length=3)
    target_shot_type: str
    model_set_id: UUID | None = None
    pose_reference_id: UUID | None = None
    style_reference_ids: list[UUID] = Field(default_factory=list, max_length=2)
    prompt: str = Field(min_length=10, max_length=1000)
    restrictions: str = Field(default="", max_length=500)
    aspect_ratio: str = "1:1"
    variant_count: int = Field(default=4, ge=1, le=4)
    seed: int | None = None
    parent_generation_id: UUID | None = None


async def _rate_gen(session: SessionDep, user_id: UUID) -> None:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    key = f"gen:{user_id}"
    row = (
        await session.execute(
            select(RateLimitBucket).where(
                RateLimitBucket.bucket_key == key, RateLimitBucket.window_start == now
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(RateLimitBucket(bucket_key=key, window_start=now, count=1))
        return
    if row.count >= 30:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "Generation rate limit",
            status_code=429,
            details={"retry_after": 3600},
        )
    row.count += 1


@router.post("/generations/preflight")
async def preflight(
    body: GenerationBody, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    _product, _brand, issues, final_prompt, rights, counts, price = await _prepare(
        body, ctx, session, settings
    )
    estimated = None
    if price is not None:
        estimated = str((price * body.variant_count).quantize(Decimal("0.01")))
    return {
        "final_prompt": final_prompt,
        "issues": issues,
        "rights_check": rights,
        "estimated_cost_eur": estimated,
        "reference_counts": counts,
    }


@router.post("/generations")
async def create_generation(
    body: GenerationBody, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    await _rate_gen(session, ctx.user.id)
    _product, brand, issues, final_prompt, rights, _counts, price = await _prepare(
        body, ctx, session, settings
    )
    non_rights_blocking = [
        i for i in issues if i.get("blocking") and i.get("code") != "rights_not_cleared"
    ]
    if non_rights_blocking:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            non_rights_blocking[0].get("message_key") or "Validation failed",
            status_code=422,
            details=non_rights_blocking[0].get("details") or {},
        )
    status = "queued"
    if not rights.get("ok"):
        status = "blocked_rights"
    image_cfg = (brand.provider_config or {}).get("image") or {}
    provider_key = str(image_cfg.get("provider") or settings.image_provider)
    provider_model = str(image_cfg.get("model") or settings.image_provider_model)
    gen = Generation(
        brand_id=ctx.brand_id,
        product_id=body.product_id,
        requested_by=ctx.user.id,
        parent_generation_id=body.parent_generation_id,
        provider=provider_key,
        provider_model=provider_model,
        target_shot_type=body.target_shot_type,
        model_set_id=body.model_set_id,
        pose_reference_id=body.pose_reference_id,
        style_reference_ids=body.style_reference_ids,
        garment_version_ids=body.garment_version_ids,
        prompt=body.prompt,
        restrictions=body.restrictions,
        final_prompt=final_prompt,
        aspect_ratio=body.aspect_ratio,
        variant_count=body.variant_count,
        seed=body.seed,
        rights_check=rights,
        status=status,
    )
    session.add(gen)
    await session.flush()
    if status == "blocked_rights":
        await session.commit()
        raise AppError(
            ErrorCode.RIGHTS_NOT_CLEARED,
            "Rights not cleared",
            status_code=422,
            details={"subjects": rights.get("subjects", []), "generation_id": str(gen.id)},
        )
    job = await enqueue_job(
        session,
        brand_id=ctx.brand_id,
        type="generate_images",
        entity_type="generation",
        entity_id=gen.id,
        requested_by=ctx.user.id,
    )
    await session.commit()
    return {
        "id": str(gen.id),
        "status": gen.status,
        "job_id": str(job.id),
        "final_prompt": final_prompt,
        "estimated_cost_eur": str((price * body.variant_count).quantize(Decimal("0.01")))
        if price is not None
        else None,
    }


@router.get("/generations/{generation_id}")
async def get_generation(
    generation_id: UUID,
    ctx: BrandAuthDep,
    session: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    from kitframe.media.storage import presign_get

    gen = await session.get(Generation, generation_id)
    if gen is None or gen.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    assets = (
        await session.execute(select(Asset).where(Asset.generation_id == gen.id))
    ).scalars().all()
    out_assets: list[dict[str, Any]] = []
    for a in assets:
        url = None
        qc_result = None
        if a.current_version_id:
            version = await session.get(AssetVersion, a.current_version_id)
            if version is not None:
                url = presign_get(settings, version.storage_key)
                run = (
                    await session.execute(
                        select(QCRun)
                        .where(QCRun.asset_version_id == version.id)
                        .order_by(QCRun.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                qc_result = run.result if run else None
        out_assets.append(
            {
                "id": str(a.id),
                "status": a.status,
                "shot_type": a.shot_type,
                "url": url,
                "qc_result": qc_result,
            }
        )
    return {**_ser(gen), "assets": out_assets}


@router.get("/generations")
async def list_generations(
    ctx: BrandAuthDep,
    session: SessionDep,
    product_id: UUID,
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Generation)
            .where(Generation.brand_id == ctx.brand_id, Generation.product_id == product_id)
            .order_by(Generation.created_at.desc())
        )
    ).scalars().all()
    return {"data": [_ser(g) for g in rows]}


async def _prepare(
    body: GenerationBody, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep
):
    product = await session.get(Product, body.product_id)
    if product is None or product.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Product not found", status_code=404)
    if not await can(session, ctx, "studio.use", product=product):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    if product.current_phase != "visuals" and ctx.membership.role not in ("admin", "owner"):
        raise AppError(ErrorCode.PHASE_LOCKED, "Product not in visuals", status_code=409)
    brand = await session.get(Brand, ctx.brand_id)
    assert brand is not None

    allowed_ratios = {"1:1", "4:5", "3:4", "2:3", "9:16", "16:9"}
    if body.aspect_ratio not in allowed_ratios:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid aspect ratio", status_code=422)

    # Validate garment versions belong to product and are real photos
    for vid in body.garment_version_ids:
        version = await session.get(AssetVersion, vid)
        if version is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Garment version not found", status_code=422)
        asset = await session.get(Asset, version.asset_id)
        if asset is None or asset.product_id != product.id or asset.origin != "real_photo":
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Garment references must be real photos of the product",
                status_code=422,
            )

    n_model = 0
    if body.model_set_id:
        model_set = await session.get(ModelReferenceSet, body.model_set_id)
        if model_set is None or model_set.brand_id != ctx.brand_id or model_set.status != "active":
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid model set", status_code=422)
        model_imgs = (
            await session.execute(
                select(ReferenceImage)
                .where(
                    ReferenceImage.set_id == body.model_set_id,
                    ReferenceImage.validation_status == "valid",
                )
                .order_by(ReferenceImage.sort_order, ReferenceImage.created_at)
                .limit(3)
            )
        ).scalars().all()
        n_model = len(model_imgs)

    n_pose = 1 if body.pose_reference_id else 0
    if body.pose_reference_id:
        pose = await session.get(ReferenceImage, body.pose_reference_id)
        if pose is None or pose.brand_id != ctx.brand_id or pose.kind != "pose":
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid pose reference", status_code=422)

    n_style = len(body.style_reference_ids)
    for sid in body.style_reference_ids:
        style = await session.get(ReferenceImage, sid)
        if style is None or style.brand_id != ctx.brand_id or style.kind != "style":
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid style reference", status_code=422)

    n_garment = len(body.garment_version_ids)
    total_refs = n_garment + n_model + n_pose + n_style
    image_cfg = (brand.provider_config or {}).get("image") or {}
    provider = get_image_provider(settings, image_cfg)
    max_refs = getattr(provider, "max_reference_images", 8)

    issues: list[dict[str, Any]] = []
    if total_refs > max_refs:
        issues.append(
            {
                "code": "too_many_references",
                "blocking": True,
                "message_key": "studio.too_many_references",
                "details": {"max": max_refs, "count": total_refs},
            }
        )

    rights = await check_rights(
        session,
        brand_id=ctx.brand_id,
        model_set_id=body.model_set_id,
        prompt=body.prompt,
        restrictions=body.restrictions,
    )
    if not rights["ok"]:
        issues.append(
            {
                "code": "rights_not_cleared",
                "blocking": True,
                "message_key": "studio.rights",
                "subjects": rights.get("subjects"),
            }
        )

    final_prompt = compose_final_prompt(
        generation_rules=brand.generation_rules or "",
        prompt=body.prompt,
        restrictions=body.restrictions,
        aspect_ratio=body.aspect_ratio,
        shot_type=body.target_shot_type,
        n_garment=n_garment,
        n_model=n_model,
        n_pose=n_pose,
        n_style=n_style,
    )
    price = None
    raw_price = image_cfg.get("price_per_image_eur")
    if raw_price is not None:
        price = Decimal(str(raw_price))
    counts = {
        "garment": n_garment,
        "model": n_model,
        "pose": n_pose,
        "style": n_style,
        "total": total_refs,
        "max": max_refs,
    }
    return product, brand, issues, final_prompt, rights, counts, price


def _ser(g: Generation) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "product_id": str(g.product_id),
        "status": g.status,
        "prompt": g.prompt,
        "restrictions": g.restrictions,
        "final_prompt": g.final_prompt,
        "aspect_ratio": g.aspect_ratio,
        "variant_count": g.variant_count,
        "target_shot_type": g.target_shot_type,
        "model_set_id": str(g.model_set_id) if g.model_set_id else None,
        "pose_reference_id": str(g.pose_reference_id) if g.pose_reference_id else None,
        "style_reference_ids": [str(x) for x in (g.style_reference_ids or [])],
        "garment_version_ids": [str(x) for x in (g.garment_version_ids or [])],
        "seed": g.seed,
        "images_returned": g.images_returned,
        "cost_eur": str(g.cost_eur) if g.cost_eur is not None else None,
        "created_at": g.created_at.isoformat(),
        "error_detail": g.error_detail,
        "provider": g.provider,
        "provider_model": g.provider_model,
    }
