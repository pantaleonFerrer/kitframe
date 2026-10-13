from __future__ import annotations

import hashlib
import io
from typing import Literal

import httpx
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel

from app.config import Settings, get_settings

ImageOperation = Literal["remove_background", "ghost_mannequin", "retouch"]


class ProcessImageRequest(BaseModel):
    asset_url: str
    operation: ImageOperation


class ProcessImageResponse(BaseModel):
    processed_url: str
    operation: ImageOperation


async def fetch_image_bytes(url: str, timeout: float) -> bytes:
    if url.startswith("file://"):
        path = url[7:]
        with open(path, "rb") as handle:
            return handle.read()
    if url.startswith("mock://"):
        image = Image.new("RGBA", (64, 64), (200, 40, 40, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _fixture_url(operation: str, source_url: str) -> str:
    digest = hashlib.sha256(f"{operation}:{source_url}".encode("utf-8")).hexdigest()[:16]
    return f"mock://processed/{operation}/{digest}.png"


def remove_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    arr = np.asarray(rgba).copy()
    rgb = arr[:, :, :3].astype(np.float64)
    luminance = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    corners = np.concatenate(
        [
            rgb[0, 0],
            rgb[0, -1],
            rgb[-1, 0],
            rgb[-1, -1],
        ]
    ).reshape(4, 3)
    bg = corners.mean(axis=0)
    dist = np.linalg.norm(rgb - bg, axis=2)
    alpha = np.where((dist < 28.0) | (luminance > 245.0), 0, 255).astype(np.uint8)
    arr[:, :, 3] = alpha
    return Image.fromarray(arr, mode="RGBA")


def ghost_mannequin(image: Image.Image) -> Image.Image:
    base = remove_background(image)
    arr = np.asarray(base).copy()
    alpha = arr[:, :, 3]
    mask = alpha > 0
    if mask.any():
        rgb = arr[:, :, :3].astype(np.float64)
        mean = rgb[mask].mean(axis=0)
        center = (arr.shape[0] // 2, arr.shape[1] // 2)
        yy, xx = np.ogrid[: arr.shape[0], : arr.shape[1]]
        hole = (yy - center[0]) ** 2 + (xx - center[1]) ** 2 <= (min(arr.shape[0], arr.shape[1]) // 8) ** 2
        fill = hole & mask
        arr[fill, 0] = int(mean[0])
        arr[fill, 1] = int(mean[1])
        arr[fill, 2] = int(mean[2])
        arr[fill, 3] = 255
    return Image.fromarray(arr, mode="RGBA")


def retouch(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    sharpened = rgb.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    contrasted = ImageEnhance.Contrast(sharpened).enhance(1.08)
    brightened = ImageEnhance.Brightness(contrasted).enhance(1.03)
    return ImageOps.autocontrast(brightened, cutoff=1)


def apply_operation(image: Image.Image, operation: ImageOperation) -> Image.Image:
    if operation == "remove_background":
        return remove_background(image)
    if operation == "ghost_mannequin":
        return ghost_mannequin(image)
    return retouch(image)


async def process_image(request: ProcessImageRequest, settings: Settings | None = None) -> ProcessImageResponse:
    settings = settings or get_settings()
    raw = await fetch_image_bytes(request.asset_url, settings.image_ops_timeout_seconds)
    image = Image.open(io.BytesIO(raw))
    apply_operation(image, request.operation)
    return ProcessImageResponse(
        processed_url=_fixture_url(request.operation, request.asset_url),
        operation=request.operation,
    )
