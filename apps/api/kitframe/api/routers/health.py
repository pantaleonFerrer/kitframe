from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from kitframe.api.deps import SessionDep, SettingsDep
from kitframe.errors import AppError, ErrorCode
from kitframe.media.storage import storage_reachable

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: SessionDep, settings: SettingsDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError(ErrorCode.INTERNAL_ERROR, "database unavailable", status_code=503) from exc
    if not storage_reachable(settings):
        raise AppError(ErrorCode.INTERNAL_ERROR, "storage unavailable", status_code=503)
    return {"status": "ready"}
