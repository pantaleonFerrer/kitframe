from __future__ import annotations

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from kitframe.auth.permissions import AuthContext, get_membership
from kitframe.auth.tokens import decode_access_token
from kitframe.db.models import BrandMembership, User
from kitframe.db.session import get_session
from kitframe.errors import AppError, ErrorCode
from kitframe.settings import Settings, get_settings


async def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(ErrorCode.UNAUTHORIZED, "Missing bearer token", status_code=401)
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token, settings)
    user = await session.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise AppError(ErrorCode.UNAUTHORIZED, "User not found", status_code=401)
    if user.token_version != payload.get("tv"):
        raise AppError(ErrorCode.TOKEN_INVALID, "Token revoked", status_code=401)
    return user


async def get_auth_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    x_brand_id: Annotated[str | None, Header(alias="X-Brand-Id")] = None,
) -> AuthContext:
    membership: BrandMembership | None = None
    brand_id: UUID | None = None
    if x_brand_id:
        brand_id = UUID(x_brand_id)
        membership = await get_membership(session, user.id, brand_id)
        if membership is None:
            raise AppError(ErrorCode.FORBIDDEN, "Not a member of this brand", status_code=403)
    return AuthContext(
        user=user,
        brand_id=brand_id,
        membership=membership,
        request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
    )


async def require_brand(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
    if ctx.brand_id is None or ctx.membership is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "X-Brand-Id required", status_code=422)
    return ctx


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UserDep = Annotated[User, Depends(get_current_user)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
BrandAuthDep = Annotated[AuthContext, Depends(require_brand)]
