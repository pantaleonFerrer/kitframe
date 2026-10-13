from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.db.models import RefreshToken, User
from kitframe.errors import AppError, ErrorCode
from kitframe.settings import Settings

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


COMMON_PASSWORDS = {
    "password",
    "password123",
    "123456789012",
    "qwertyuiopas",
    "kitframe1234",
}


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Password must be at least 12 characters", status_code=422)
    if password.lower() in COMMON_PASSWORDS:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Password is too common", status_code=422)
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user: User, settings: Settings) -> str:
    payload = {
        "sub": str(user.id),
        "tv": user.token_version,
        "exp": datetime.now(UTC) + timedelta(minutes=15),
        "iat": datetime.now(UTC),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError(ErrorCode.TOKEN_INVALID, "Invalid access token", status_code=401) from exc
    if payload.get("type") != "access":
        raise AppError(ErrorCode.TOKEN_INVALID, "Invalid access token", status_code=401)
    return payload


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_refresh_token(session: AsyncSession, user_id: UUID, family_id: UUID | None = None) -> str:
    raw = secrets.token_urlsafe(48)
    token = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        family_id=family_id or uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(token)
    await session.flush()
    return raw


async def rotate_refresh_token(session: AsyncSession, raw: str) -> tuple[User, str]:
    token_hash = hash_token(raw)
    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    existing = result.scalar_one_or_none()
    if existing is None:
        raise AppError(ErrorCode.TOKEN_INVALID, "Invalid refresh token", status_code=401)
    if existing.revoked_at is not None:
        await session.execute(
            RefreshToken.__table__.update()
            .where(RefreshToken.family_id == existing.family_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()
        raise AppError(ErrorCode.TOKEN_INVALID, "Refresh token reuse detected", status_code=401)
    if existing.expires_at < datetime.now(UTC):
        raise AppError(ErrorCode.TOKEN_INVALID, "Refresh token expired", status_code=401)

    user = await session.get(User, existing.user_id)
    if user is None or not user.is_active:
        raise AppError(ErrorCode.UNAUTHORIZED, "User inactive", status_code=401)

    existing.revoked_at = datetime.now(UTC)
    new_raw = await issue_refresh_token(session, user.id, family_id=existing.family_id)
    new_result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(new_raw))
    )
    new_token = new_result.scalar_one()
    existing.replaced_by = new_token.id
    await session.flush()
    return user, new_raw


async def revoke_refresh_family(session: AsyncSession, raw: str) -> None:
    token_hash = hash_token(raw)
    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    existing = result.scalar_one_or_none()
    if existing is None:
        return
    await session.execute(
        RefreshToken.__table__.update()
        .where(RefreshToken.family_id == existing.family_id)
        .values(revoked_at=datetime.now(UTC))
    )
