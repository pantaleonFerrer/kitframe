from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kitframe.api.deps import BrandAuthDep, SettingsDep
from kitframe.media.storage import presign_put

router = APIRouter(tags=["uploads"])


class PresignBody(BaseModel):
    purpose: str
    file_name: str
    content_type: str
    size: int = Field(gt=0, le=50 * 1024 * 1024)


@router.post("/uploads/presign")
async def presign(body: PresignBody, ctx: BrandAuthDep, settings: SettingsDep) -> dict[str, Any]:
    max_size = 25 * 1024 * 1024 if body.purpose in ("source_document",) else 50 * 1024 * 1024
    if body.size > max_size:
        from kitframe.errors import AppError, ErrorCode
        raise AppError(ErrorCode.FILE_TOO_LARGE, "File too large", status_code=413)
    return presign_put(
        settings,
        brand_id=str(ctx.brand_id),
        kind=body.purpose,
        file_name=body.file_name,
        content_type=body.content_type,
        max_size=max_size,
    )
