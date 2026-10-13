from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import (
    Asset,
    AssetVersion,
    Brand,
    ChannelSpec,
    Product,
    QCOverride,
    QCRun,
    RightsRecord,
    ShopifyConnection,
    Variant,
)


async def evaluate_exit_criteria(
    session: AsyncSession,
    product: Product,
    brand: Brand,
    phase: str,
) -> list[dict[str, Any]]:
    if phase == "data":
        return await _data_criteria(session, product, brand)
    if phase == "visuals":
        return await _visuals_criteria(session, product, brand)
    if phase == "retouch":
        return await _retouch_criteria(session, product, brand)
    if phase == "approval":
        base = []
        for p in ("data", "visuals", "retouch"):
            base.extend(await evaluate_exit_criteria(session, product, brand, p))
        base.extend(await _approval_criteria(session, product, brand))
        return base
    return []


async def _data_criteria(session: AsyncSession, product: Product, brand: Brand) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fields = brand.taxonomy_schema.get("fields", [])
    data = product.structured_data or {}
    conf = product.field_confidence or {}
    confirmed = set(product.confirmed_fields or [])
    threshold = (brand.qc_config or {}).get("extraction", {}).get("confirm_below_confidence", 0.85)

    for field in fields:
        if not field.get("required"):
            continue
        key = field["key"]
        value = data.get(key)
        ok = value is not None and value != "" and value != []
        out.append(
            {
                "code": f"required_field:{key}",
                "message_key": "criteria.required_field",
                "ok": ok,
                "details": {"field": key},
            }
        )

    for key, score in conf.items():
        if float(score) < threshold and key not in confirmed:
            out.append(
                {
                    "code": f"confirm_field:{key}",
                    "message_key": "criteria.confirm_field",
                    "ok": False,
                    "details": {"field": key, "confidence": score},
                }
            )
        elif float(score) < threshold:
            out.append(
                {
                    "code": f"confirm_field:{key}",
                    "message_key": "criteria.confirm_field",
                    "ok": True,
                    "details": {"field": key, "confidence": score},
                }
            )

    variants = (
        await session.execute(select(Variant).where(Variant.product_id == product.id))
    ).scalars().all()
    out.append(
        {
            "code": "has_variants",
            "message_key": "criteria.has_variants",
            "ok": len(variants) >= 1,
        }
    )
    variants_ok = all(v.sku and v.price_eur is not None for v in variants) if variants else False
    out.append(
        {
            "code": "variants_complete",
            "message_key": "criteria.variants_complete",
            "ok": variants_ok,
        }
    )

    content = product.content or {}
    for locale in ("es", "ca", "en"):
        loc = content.get(locale) or {}
        name_ok = bool(loc.get("name") and loc.get("description"))
        seo_title = loc.get("seo_title") or ""
        seo_meta = loc.get("seo_meta") or ""
        out.append(
            {
                "code": f"content_name:{locale}",
                "message_key": "criteria.content_name",
                "ok": name_ok,
                "details": {"locale": locale},
            }
        )
        out.append(
            {
                "code": f"seo_title:{locale}",
                "message_key": "criteria.seo_title",
                "ok": bool(seo_title) and len(seo_title) <= 70,
                "details": {"locale": locale},
            }
        )
        out.append(
            {
                "code": f"seo_meta:{locale}",
                "message_key": "criteria.seo_meta",
                "ok": bool(seo_meta) and len(seo_meta) <= 160,
                "details": {"locale": locale},
            }
        )
    return out


async def _visuals_criteria(session: AsyncSession, product: Product, brand: Brand) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    category = product.garment_category or (product.structured_data or {}).get("garment_category")
    required = (brand.required_shots or {}).get(category or "", [])
    assets = (
        await session.execute(
            select(Asset).where(Asset.product_id == product.id, Asset.status == "selected")
        )
    ).scalars().all()
    by_shot = {a.shot_type for a in assets}
    for shot in required:
        out.append(
            {
                "code": f"shot_selected:{shot}",
                "message_key": "criteria.shot_selected",
                "ok": shot in by_shot,
                "details": {"shot_type": shot},
            }
        )

    # Rights still cleared for selected generated assets
    generated = [a for a in assets if a.origin == "generated" and a.generation_id]
    rights_ok = True
    if generated:
        from kitframe.db.models import Generation

        for asset in generated:
            gen = await session.get(Generation, asset.generation_id)
            if gen is None:
                rights_ok = False
                break
            check = gen.rights_check or {}
            if not check.get("ok"):
                rights_ok = False
                break
            for rid in check.get("records") or []:
                rec = await session.get(RightsRecord, UUID(str(rid)))
                if rec is None or rec.status != "cleared":
                    rights_ok = False
                    break
    out.append(
        {
            "code": "rights_still_cleared",
            "message_key": "criteria.rights_still_cleared",
            "ok": rights_ok,
        }
    )
    return out


async def _retouch_criteria(session: AsyncSession, product: Product, brand: Brand) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    assets = (
        await session.execute(
            select(Asset).where(Asset.product_id == product.id, Asset.status == "selected")
        )
    ).scalars().all()
    channels = (
        await session.execute(select(ChannelSpec).where(ChannelSpec.brand_id == product.brand_id))
    ).scalars().all()
    min_short = min((min(c.width_px, c.height_px) for c in channels), default=0)

    for asset in assets:
        version = None
        if asset.current_version_id:
            version = await session.get(AssetVersion, asset.current_version_id)
        qc_ok = False
        if version:
            run = (
                await session.execute(
                    select(QCRun)
                    .where(QCRun.asset_version_id == version.id, QCRun.status == "completed")
                    .order_by(QCRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            override = (
                await session.execute(
                    select(QCOverride).where(QCOverride.asset_version_id == version.id).limit(1)
                )
            ).scalar_one_or_none()
            qc_ok = (run is not None and run.result == "pass") or override is not None
        out.append(
            {
                "code": f"qc_pass:{asset.id}",
                "message_key": "criteria.qc_pass",
                "ok": qc_ok,
                "details": {"asset_id": str(asset.id)},
            }
        )
        alt = (asset.alt_text or {}).get("es")
        out.append(
            {
                "code": f"alt_text:{asset.id}",
                "message_key": "criteria.alt_text",
                "ok": bool(alt),
                "details": {"asset_id": str(asset.id)},
            }
        )
        res_ok = False
        if version:
            res_ok = min(version.width, version.height) >= min_short if min_short else True
        out.append(
            {
                "code": f"resolution:{asset.id}",
                "message_key": "criteria.resolution",
                "ok": res_ok,
                "details": {"asset_id": str(asset.id)},
            }
        )
    return out


async def _approval_criteria(session: AsyncSession, product: Product, brand: Brand) -> list[dict[str, Any]]:
    env = brand.active_shopify_environment
    conn = (
        await session.execute(
            select(ShopifyConnection).where(
                ShopifyConnection.brand_id == brand.id, ShopifyConnection.environment == env
            )
        )
    ).scalar_one_or_none()
    return [
        {
            "code": "shopify_configured",
            "message_key": "criteria.shopify_configured",
            "ok": conn is not None and (conn.last_check_ok is not False),
        },
        {
            "code": "shopify_locales",
            "message_key": "criteria.shopify_locales",
            "ok": True if conn is None else bool((conn.last_check_detail or {}).get("locales_ok", True)),
        },
    ]
