from __future__ import annotations

import hashlib
import io
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.image_ops import fetch_image_bytes


class Point2D(BaseModel):
    x: float
    y: float


class CompositeCrestRequest(BaseModel):
    base_image_url: str
    crest_asset_url: str
    target_quad: list[Point2D] = Field(min_length=4, max_length=4)
    source_quad: list[Point2D] | None = None


class CompositeCrestResponse(BaseModel):
    composited_url: str
    method: str


def _has_cv2() -> bool:
    try:
        import cv2

        return cv2 is not None
    except Exception:
        return False


def _quad_to_np(quad: list[Point2D]) -> np.ndarray:
    return np.array([[p.x, p.y] for p in quad], dtype=np.float32)


def warp_crest_homography(
    base: Image.Image,
    crest: Image.Image,
    source_quad: np.ndarray,
    target_quad: np.ndarray,
) -> tuple[Image.Image, str]:
    if _has_cv2():
        import cv2

        base_rgba = np.array(base.convert("RGBA"))
        crest_rgba = np.array(crest.convert("RGBA"))
        matrix = cv2.getPerspectiveTransform(source_quad, target_quad)
        warped = cv2.warpPerspective(
            crest_rgba,
            matrix,
            (base_rgba.shape[1], base_rgba.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
        alpha = warped[:, :, 3:4].astype(np.float64) / 255.0
        out = base_rgba.astype(np.float64)
        out[:, :, :3] = (1.0 - alpha) * out[:, :, :3] + alpha * warped[:, :, :3]
        out[:, :, 3] = np.maximum(out[:, :, 3], warped[:, :, 3])
        return Image.fromarray(out.astype(np.uint8), mode="RGBA"), "homography"

    base_rgba = base.convert("RGBA")
    crest_rgba = crest.convert("RGBA")
    xs = target_quad[:, 0]
    ys = target_quad[:, 1]
    min_x, max_x = float(xs.min()), float(xs.max())
    min_y, max_y = float(ys.min()), float(ys.max())
    width = max(1, int(round(max_x - min_x)))
    height = max(1, int(round(max_y - min_y)))
    resized = crest_rgba.resize((width, height), Image.Resampling.BICUBIC)
    composed = base_rgba.copy()
    composed.alpha_composite(resized, dest=(int(round(min_x)), int(round(min_y))))
    return composed, "affine_fallback"


async def composite_crest(
    request: CompositeCrestRequest,
    settings: Settings | None = None,
) -> CompositeCrestResponse:
    settings = settings or get_settings()
    timeout = settings.image_ops_timeout_seconds
    base_bytes = await fetch_image_bytes(request.base_image_url, timeout)
    crest_bytes = await fetch_image_bytes(request.crest_asset_url, timeout)
    base = Image.open(io.BytesIO(base_bytes))
    crest = Image.open(io.BytesIO(crest_bytes))
    if request.source_quad is not None:
        source = _quad_to_np(request.source_quad)
    else:
        w, h = crest.size
        source = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    target = _quad_to_np(request.target_quad)
    _, method = warp_crest_homography(base, crest, source, target)
    digest = hashlib.sha256(
        f"{request.base_image_url}:{request.crest_asset_url}:{method}".encode("utf-8")
    ).hexdigest()[:16]
    return CompositeCrestResponse(
        composited_url=f"mock://composited/{digest}.png",
        method=method,
    )
