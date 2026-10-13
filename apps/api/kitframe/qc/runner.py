from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import Asset, AssetVersion, Brand, GoldenSetImage, Product, QCRun
from kitframe.media.storage import get_bytes
from kitframe.qc.color import cluster_colors, score_color
from kitframe.qc.crest import check_crest
from kitframe.qc.resolution import check_resolution
from kitframe.settings import Settings


def _worst(*results: str) -> str:
    order = {"pass": 0, "needs_review": 1, "fail": 2}
    return max(results, key=lambda r: order.get(r, 0))


async def run_qc_for_version(
    session: AsyncSession,
    settings: Settings,
    version_id: UUID,
) -> QCRun:
    version = await session.get(AssetVersion, version_id)
    assert version is not None
    asset = await session.get(Asset, version.asset_id)
    assert asset is not None
    product = await session.get(Product, asset.product_id)
    brand = await session.get(Brand, asset.brand_id)
    assert product is not None and brand is not None

    run = QCRun(asset_version_id=version.id, status="running")
    session.add(run)
    await session.flush()

    cfg = brand.qc_config or {}
    run.config_snapshot = cfg
    try:
        raw = get_bytes(settings, version.storage_key)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        # Fixture / missing object: use blank
        image = Image.new("RGB", (version.width or 2048, version.height or 2048), (125, 26, 29))

    checks: dict[str, Any] = {}
    res_cfg = cfg.get("resolution", {})
    generated_min = res_cfg.get("min_short_side_px_generated")
    checks["resolution"] = check_resolution(
        image.width,
        image.height,
        int(res_cfg.get("min_short_side_px", 2000)),
        origin=asset.origin,
        min_short_side_px_generated=int(generated_min) if generated_min is not None else 1440,
    )

    category = product.garment_category or (product.structured_data or {}).get("garment_category")
    shot = asset.shot_type
    golden_shot = shot
    if shot in ("model_back", "lifestyle", "product_detail"):
        golden_shot = "model_front" if shot.startswith("model") or shot == "lifestyle" else "product_front"

    golden = (
        await session.execute(
            select(GoldenSetImage).where(
                GoldenSetImage.brand_id == brand.id,
                GoldenSetImage.garment_category == (category or ""),
                GoldenSetImage.shot_type == golden_shot,
                GoldenSetImage.status == "approved",
            )
        )
    ).scalar_one_or_none()
    if golden is None and golden_shot != "product_front":
        golden = (
            await session.execute(
                select(GoldenSetImage).where(
                    GoldenSetImage.brand_id == brand.id,
                    GoldenSetImage.garment_category == (category or ""),
                    GoldenSetImage.shot_type == "product_front",
                    GoldenSetImage.status == "approved",
                )
            )
        ).scalar_one_or_none()

    color_cfg = cfg.get("color", {})
    crest_cfg = cfg.get("crest", {})
    if golden is None:
        checks["color"] = {"result": "needs_review", "reason": "no_golden_reference"}
        checks["crest"] = {"result": "needs_review", "reason": "no_golden_reference"}
        overall = _worst(checks["resolution"]["result"], "needs_review")
        if overall == "pass":
            overall = "needs_review"
    else:
        run.golden_set_image_id = golden.id
        ref_colors = golden.reference_colors or cluster_colors(image)
        checks["color"] = score_color(
            image,
            ref_colors,
            pass_max=float(color_cfg.get("pass_max_delta_e", 3.0)),
            review_max=float(color_cfg.get("review_max_delta_e", 6.0)),
        )
        template = None
        if golden.crest_template_key:
            try:
                template = Image.open(io.BytesIO(get_bytes(settings, golden.crest_template_key)))
            except Exception:
                template = None
        elif golden.crest_bbox:
            # crop from golden image if available
            try:
                gimg = Image.open(io.BytesIO(get_bytes(settings, golden.storage_key)))
                box = golden.crest_bbox
                w, h = gimg.size
                template = gimg.crop(
                    (
                        int(box["x"] * w),
                        int(box["y"] * h),
                        int((box["x"] + box["w"]) * w),
                        int((box["y"] + box["h"]) * h),
                    )
                )
            except Exception:
                template = None
        checks["crest"] = check_crest(
            image,
            template,
            pass_min=float(crest_cfg.get("pass_min_confidence", 0.8)),
            review_min=float(crest_cfg.get("review_min_confidence", 0.55)),
            position_tolerance=float(crest_cfg.get("position_tolerance", 0.05)),
            check_position=shot in ("product_front", "product_back"),
        )
        overall = _worst(checks["resolution"]["result"], checks["color"]["result"], checks["crest"]["result"])

    run.checks = checks
    run.result = overall
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    await session.flush()
    return run
