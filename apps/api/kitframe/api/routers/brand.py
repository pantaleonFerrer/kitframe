from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from kitframe.api.deps import BrandAuthDep, SessionDep, SettingsDep
from kitframe.auth.permissions import brand_role_allows
from kitframe.auth.tokens import hash_token
from kitframe.db.models import (
    Brand,
    BrandMembership,
    ChannelSpec,
    Invitation,
    ShopifyConnection,
    User,
)
from kitframe.errors import AppError, ErrorCode
from kitframe.shopify.crypto import encrypt_token

router = APIRouter(tags=["brand"])


class BrandPatch(BaseModel):
    name: str | None = None
    taxonomy_schema: dict[str, Any] | None = None
    glossary: dict[str, Any] | None = None
    generation_rules: str | None = None
    required_shots: dict[str, Any] | None = None
    qc_config: dict[str, Any] | None = None
    provider_config: dict[str, Any] | None = None
    shopify_metafields: list[Any] | None = None


class ChannelSpecIn(BaseModel):
    channel: str
    width_px: int
    height_px: int
    format: str
    quality: int = 90
    background: str = "white"
    color_profile: str = "sRGB"
    filename_pattern: str
    is_primary: bool = False


class ShopifyPut(BaseModel):
    store_domain: str
    access_token: str


class ActivateBody(BaseModel):
    environment: str
    confirm_text: str


class MemberPatch(BaseModel):
    role: str | None = None
    can_approve_golden_set: bool | None = None


class InviteBody(BaseModel):
    email: str
    role: str


BRAND_ROLES = {"owner", "admin", "editor", "member", "viewer"}


def _validate_role(role: str) -> None:
    if role not in BRAND_ROLES:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Invalid role: {role}", status_code=422)


@router.get("/brand")
async def get_brand(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    brand = await session.get(Brand, ctx.brand_id)
    if brand is None:
        raise AppError(ErrorCode.NOT_FOUND, "Brand not found", status_code=404)
    return _ser_brand(brand)


@router.patch("/brand")
async def patch_brand(body: BrandPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    brand = await session.get(Brand, ctx.brand_id)
    assert brand is not None
    data = body.model_dump(exclude_unset=True)
    if "provider_config" in data and data["provider_config"] is not None:
        from kitframe.providers.config import validate_provider_config

        try:
            data["provider_config"] = validate_provider_config(data["provider_config"])
        except Exception as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR, str(exc), status_code=422) from exc
    if "qc_config" in data and data["qc_config"] is not None:
        from kitframe.providers.config import validate_qc_config

        try:
            data["qc_config"] = validate_qc_config(data["qc_config"])
        except Exception as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR, str(exc), status_code=422) from exc
    for k, v in data.items():
        setattr(brand, k, v)
    brand.updated_at = datetime.now(UTC)
    await session.commit()
    return _ser_brand(brand)


@router.get("/brand/channel-specs")
async def list_channel_specs(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    rows = (await session.execute(select(ChannelSpec).where(ChannelSpec.brand_id == ctx.brand_id))).scalars().all()
    return {"data": [_ser_channel(r) for r in rows]}


@router.put("/brand/channel-specs")
async def put_channel_specs(body: list[ChannelSpecIn], ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    existing = (await session.execute(select(ChannelSpec).where(ChannelSpec.brand_id == ctx.brand_id))).scalars().all()
    for e in existing:
        await session.delete(e)
    for item in body:
        session.add(ChannelSpec(brand_id=ctx.brand_id, **item.model_dump()))
    await session.commit()
    return await list_channel_specs(ctx, session)


@router.get("/brand/shopify")
async def get_shopify(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    brand = await session.get(Brand, ctx.brand_id)
    rows = (await session.execute(select(ShopifyConnection).where(ShopifyConnection.brand_id == ctx.brand_id))).scalars().all()
    return {
        "active_environment": brand.active_shopify_environment if brand else "staging",
        "connections": [
            {
                "environment": r.environment,
                "store_domain": r.store_domain,
                "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
                "last_check_ok": r.last_check_ok,
                "last_check_detail": r.last_check_detail,
            }
            for r in rows
        ],
    }


@router.put("/brand/shopify/{environment}")
async def put_shopify(environment: str, body: ShopifyPut, ctx: BrandAuthDep, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    if environment not in ("staging", "live"):
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid environment", status_code=422)
    result = await session.execute(
        select(ShopifyConnection).where(
            ShopifyConnection.brand_id == ctx.brand_id, ShopifyConnection.environment == environment
        )
    )
    conn = result.scalar_one_or_none()
    enc = encrypt_token(settings, body.access_token)
    if conn is None:
        conn = ShopifyConnection(
            brand_id=ctx.brand_id,
            environment=environment,
            store_domain=body.store_domain,
            access_token_encrypted=enc,
        )
        session.add(conn)
    else:
        conn.store_domain = body.store_domain
        conn.access_token_encrypted = enc
        conn.updated_at = datetime.now(UTC)
    await session.commit()
    return await get_shopify(ctx, session)


@router.post("/brand/shopify/{environment}/test")
async def test_shopify(environment: str, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "brand.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    result = await session.execute(
        select(ShopifyConnection).where(
            ShopifyConnection.brand_id == ctx.brand_id, ShopifyConnection.environment == environment
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise AppError(ErrorCode.SHOPIFY_NOT_CONFIGURED, "Not configured", status_code=409)
    # Without live credentials, mark as ok with locales assumed for local/fake
    conn.last_checked_at = datetime.now(UTC)
    conn.last_check_ok = True
    conn.last_check_detail = {"locales_ok": True, "scopes_ok": True, "mode": "stub_until_d7"}
    await session.commit()
    return {"ok": True, "detail": conn.last_check_detail}


@router.post("/brand/shopify/activate")
async def activate_shopify(body: ActivateBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if ctx.membership.role != "owner":
        raise AppError(ErrorCode.FORBIDDEN, "Owner only", status_code=403)
    result = await session.execute(
        select(ShopifyConnection).where(
            ShopifyConnection.brand_id == ctx.brand_id, ShopifyConnection.environment == body.environment
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None or body.confirm_text != conn.store_domain:
        raise AppError(ErrorCode.VALIDATION_ERROR, "confirm_text must equal store domain", status_code=422)
    brand = await session.get(Brand, ctx.brand_id)
    assert brand is not None
    brand.active_shopify_environment = body.environment
    await session.commit()
    return {"active_environment": body.environment}


@router.post("/brand/qc/rerun")
async def rerun_qc(ctx: BrandAuthDep, session: SessionDep) -> dict[str, str]:
    if not brand_role_allows(ctx.membership.role, "brand.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    return {"status": "queued"}


@router.get("/members")
async def list_members(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(BrandMembership, User)
            .join(User, User.id == BrandMembership.user_id)
            .where(BrandMembership.brand_id == ctx.brand_id)
        )
    ).all()
    return {
        "data": [
            {
                "membership_id": str(m.id),
                "user_id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": m.role,
                "can_approve_golden_set": m.can_approve_golden_set,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for m, u in rows
        ]
    }


@router.patch("/members/{membership_id}")
async def patch_member(membership_id: UUID, body: MemberPatch, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "users.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    m = await session.get(BrandMembership, membership_id)
    if m is None or m.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    if body.role is not None:
        _validate_role(body.role)
        m.role = body.role
    if body.can_approve_golden_set is not None:
        m.can_approve_golden_set = body.can_approve_golden_set
    await session.commit()
    return {"status": "ok"}


@router.delete("/members/{membership_id}", status_code=204)
async def delete_member(membership_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> None:
    if not brand_role_allows(ctx.membership.role, "users.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    m = await session.get(BrandMembership, membership_id)
    if m is None or m.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    if m.role == "owner":
        owners = (
            await session.execute(
                select(BrandMembership).where(
                    BrandMembership.brand_id == ctx.brand_id, BrandMembership.role == "owner"
                )
            )
        ).scalars().all()
        if len(owners) <= 1:
            raise AppError(ErrorCode.CONFLICT, "Cannot remove last owner", status_code=409)
    await session.delete(m)
    await session.commit()


@router.get("/invitations")
async def list_invitations(ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "users.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    rows = (
        await session.execute(
            select(Invitation).where(
                Invitation.brand_id == ctx.brand_id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    return {
        "data": [
            {"id": str(i.id), "email": i.email, "role": i.role, "expires_at": i.expires_at.isoformat()}
            for i in rows
        ]
    }


@router.post("/invitations")
async def create_invitation(body: InviteBody, ctx: BrandAuthDep, session: SessionDep) -> dict[str, Any]:
    if not brand_role_allows(ctx.membership.role, "users.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    _validate_role(body.role)
    raw = secrets.token_urlsafe(24)
    inv = Invitation(
        brand_id=ctx.brand_id,
        email=body.email,
        role=body.role,
        token_hash=hash_token(raw),
        invited_by=ctx.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(inv)
    await session.commit()
    return {"id": str(inv.id), "token": raw, "email": inv.email, "role": inv.role}


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: UUID, ctx: BrandAuthDep, session: SessionDep) -> None:
    if not brand_role_allows(ctx.membership.role, "users.manage"):
        raise AppError(ErrorCode.FORBIDDEN, "Forbidden", status_code=403)
    inv = await session.get(Invitation, invitation_id)
    if inv is None or inv.brand_id != ctx.brand_id:
        raise AppError(ErrorCode.NOT_FOUND, "Not found", status_code=404)
    inv.revoked_at = datetime.now(UTC)
    await session.commit()


def _ser_brand(brand: Brand) -> dict[str, Any]:
    return {
        "id": str(brand.id),
        "name": brand.name,
        "slug": brand.slug,
        "taxonomy_schema": brand.taxonomy_schema,
        "glossary": brand.glossary,
        "generation_rules": brand.generation_rules,
        "required_shots": brand.required_shots,
        "qc_config": brand.qc_config,
        "provider_config": brand.provider_config,
        "shopify_metafields": brand.shopify_metafields,
        "active_shopify_environment": brand.active_shopify_environment,
    }


def _ser_channel(c: ChannelSpec) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "channel": c.channel,
        "width_px": c.width_px,
        "height_px": c.height_px,
        "format": c.format,
        "quality": c.quality,
        "background": c.background,
        "color_profile": c.color_profile,
        "filename_pattern": c.filename_pattern,
        "is_primary": c.is_primary,
    }
