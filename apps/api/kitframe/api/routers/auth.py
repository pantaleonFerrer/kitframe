from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Cookie, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from kitframe.api.deps import SessionDep, SettingsDep, UserDep
from kitframe.auth.permissions import serialize_user
from kitframe.auth.tokens import (
    create_access_token,
    hash_password,
    hash_token,
    issue_refresh_token,
    revoke_refresh_family,
    rotate_refresh_token,
    verify_password,
)
from kitframe.db.models import (
    Brand,
    BrandMembership,
    Invitation,
    PasswordReset,
    RateLimitBucket,
    User,
)
from kitframe.errors import AppError, ErrorCode
from kitframe.types_email import AppEmail

router = APIRouter(tags=["auth"])


class LoginBody(BaseModel):
    email: AppEmail
    password: str


class ResetBody(BaseModel):
    token: str
    password: str = Field(min_length=12)


class ForgotBody(BaseModel):
    email: AppEmail


class AcceptInviteBody(BaseModel):
    name: str
    password: str = Field(min_length=12)


class MePatch(BaseModel):
    name: str | None = None
    locale: str | None = None
    password: str | None = Field(default=None, min_length=12)
    current_password: str | None = None


async def _rate_limit(session: SessionDep, key: str, limit: int, window_minutes: int) -> None:
    now = datetime.now(UTC)
    window_start = now.replace(second=0, microsecond=0)
    result = await session.execute(
        select(RateLimitBucket).where(
            RateLimitBucket.bucket_key == key, RateLimitBucket.window_start == window_start
        )
    )
    bucket = result.scalar_one_or_none()
    if bucket is None:
        session.add(RateLimitBucket(bucket_key=key, window_start=window_start, count=1))
        await session.flush()
        return
    if bucket.count >= limit:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "Rate limit exceeded",
            status_code=429,
            details={"retry_after": window_minutes * 60},
        )
    bucket.count += 1


def _set_refresh_cookie(response: Response, raw: str, settings: SettingsDep) -> None:
    response.set_cookie(
        key="kitframe_refresh",
        value=raw,
        httponly=True,
        secure=settings.is_prod_like,
        samesite="strict",
        path="/api/v1/auth",
        max_age=30 * 24 * 3600,
    )


async def _memberships(session: SessionDep, user_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(BrandMembership, Brand)
            .join(Brand, Brand.id == BrandMembership.brand_id)
            .where(BrandMembership.user_id == user_id)
        )
    ).all()
    return [
        {
            "brand_id": str(m.brand_id),
            "brand_name": b.name,
            "brand_slug": b.slug,
            "role": m.role,
            "can_approve_golden_set": m.can_approve_golden_set,
            "membership_id": str(m.id),
        }
        for m, b in rows
    ]


@router.post("/auth/login")
async def login(
    body: LoginBody,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
    request: Request,
) -> dict[str, Any]:
    await _rate_limit(session, f"login:email:{body.email.lower()}", 5, 15)
    client = request.client.host if request.client else "unknown"
    await _rate_limit(session, f"login:ip:{client}", 20, 15)
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(user.password_hash, body.password):
        raise AppError(ErrorCode.UNAUTHORIZED, "Invalid credentials", status_code=401)
    if not user.is_active:
        raise AppError(ErrorCode.UNAUTHORIZED, "User inactive", status_code=401)
    user.last_login_at = datetime.now(UTC)
    access = create_access_token(user, settings)
    refresh = await issue_refresh_token(session, user.id)
    await session.commit()
    _set_refresh_cookie(response, refresh, settings)
    return {
        "access_token": access,
        "token_type": "bearer",
        "user": serialize_user(user, await _memberships(session, user.id)),
    }


@router.post("/auth/refresh")
async def refresh_token(
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
    kitframe_refresh: Annotated[str | None, Cookie()] = None,
    x_requested_with: Annotated[str | None, Header(alias="X-Requested-With")] = None,
) -> dict[str, Any]:
    if x_requested_with != "kitframe":
        raise AppError(ErrorCode.FORBIDDEN, "CSRF header required", status_code=403)
    if not kitframe_refresh:
        raise AppError(ErrorCode.TOKEN_INVALID, "Missing refresh cookie", status_code=401)
    user, new_raw = await rotate_refresh_token(session, kitframe_refresh)
    access = create_access_token(user, settings)
    await session.commit()
    _set_refresh_cookie(response, new_raw, settings)
    return {
        "access_token": access,
        "token_type": "bearer",
        "user": serialize_user(user, await _memberships(session, user.id)),
    }


@router.post("/auth/logout")
async def logout(
    session: SessionDep,
    response: Response,
    _user: UserDep,
    kitframe_refresh: Annotated[str | None, Cookie()] = None,
) -> Response:
    if kitframe_refresh:
        await revoke_refresh_family(session, kitframe_refresh)
        await session.commit()
    response.delete_cookie("kitframe_refresh", path="/api/v1/auth")
    return Response(status_code=204)


@router.post("/auth/forgot-password", status_code=204)
async def forgot_password(body: ForgotBody, session: SessionDep) -> None:
    await _rate_limit(session, f"forgot:{body.email.lower()}", 3, 60)
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is not None:
        raw = secrets.token_urlsafe(32)
        session.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.commit()
        # Email job would send link with raw token; logged in local for seed/dev
    else:
        await session.commit()


@router.post("/auth/reset-password")
async def reset_password(body: ResetBody, session: SessionDep) -> dict[str, str]:
    result = await session.execute(
        select(PasswordReset).where(PasswordReset.token_hash == hash_token(body.token))
    )
    row = result.scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at < datetime.now(UTC):
        raise AppError(ErrorCode.INVITATION_INVALID, "Reset token invalid", status_code=410)
    user = await session.get(User, row.user_id)
    if user is None:
        raise AppError(ErrorCode.NOT_FOUND, "User not found", status_code=404)
    user.password_hash = hash_password(body.password)
    user.token_version += 1
    row.used_at = datetime.now(UTC)
    await session.commit()
    return {"status": "ok"}


@router.get("/invitations/{token}")
async def get_invitation(token: str, session: SessionDep) -> dict[str, Any]:
    result = await session.execute(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    inv = result.scalar_one_or_none()
    if inv is None or inv.revoked_at or inv.accepted_at or inv.expires_at < datetime.now(UTC):
        raise AppError(ErrorCode.INVITATION_INVALID, "Invitation invalid", status_code=410)
    brand = await session.get(Brand, inv.brand_id)
    return {"email": inv.email, "role": inv.role, "brand_name": brand.name if brand else ""}


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    body: AcceptInviteBody,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> dict[str, Any]:
    result = await session.execute(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    inv = result.scalar_one_or_none()
    if inv is None or inv.revoked_at or inv.accepted_at or inv.expires_at < datetime.now(UTC):
        raise AppError(ErrorCode.INVITATION_INVALID, "Invitation invalid", status_code=410)
    existing = await session.execute(select(User).where(User.email == inv.email))
    user = existing.scalar_one_or_none()
    if user is None:
        user = User(email=inv.email, name=body.name, password_hash=hash_password(body.password))
        session.add(user)
        await session.flush()
    else:
        user.name = body.name
        user.password_hash = hash_password(body.password)
    session.add(
        BrandMembership(user_id=user.id, brand_id=inv.brand_id, role=inv.role)
    )
    inv.accepted_at = datetime.now(UTC)
    access = create_access_token(user, settings)
    refresh = await issue_refresh_token(session, user.id)
    await session.commit()
    _set_refresh_cookie(response, refresh, settings)
    return {
        "access_token": access,
        "token_type": "bearer",
        "user": serialize_user(user, await _memberships(session, user.id)),
    }


@router.get("/me")
async def me(user: UserDep, session: SessionDep) -> dict[str, Any]:
    return serialize_user(user, await _memberships(session, user.id))


@router.patch("/me")
async def patch_me(body: MePatch, user: UserDep, session: SessionDep) -> dict[str, Any]:
    if body.name is not None:
        user.name = body.name
    if body.locale is not None:
        if body.locale not in ("es", "ca", "en"):
            raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid locale", status_code=422)
        user.locale = body.locale
    if body.password is not None:
        if not body.current_password or not verify_password(user.password_hash, body.current_password):
            raise AppError(ErrorCode.FORBIDDEN, "Current password required", status_code=403)
        user.password_hash = hash_password(body.password)
        user.token_version += 1
    await session.commit()
    return serialize_user(user, await _memberships(session, user.id))
