from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.image_ops import fetch_image_bytes


class EmbedAssetRequest(BaseModel):
    asset_url: str
    dim: int | None = None


class EmbedAssetResponse(BaseModel):
    embedding: list[float]
    dim: int
    asset_url: str


class TrainAvatarIdentityRequest(BaseModel):
    reference_asset_urls: list[str] = Field(min_length=1)


class TrainAvatarIdentityResponse(BaseModel):
    identity_profile_ref: str


def _image_histogram_embedding(image: Image.Image, dim: int) -> list[float]:
    rgb = image.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    arr = np.asarray(rgb, dtype=np.float64) / 255.0
    hist_r, _ = np.histogram(arr[:, :, 0], bins=16, range=(0.0, 1.0), density=True)
    hist_g, _ = np.histogram(arr[:, :, 1], bins=16, range=(0.0, 1.0), density=True)
    hist_b, _ = np.histogram(arr[:, :, 2], bins=16, range=(0.0, 1.0), density=True)
    vec = np.concatenate([hist_r, hist_g, hist_b]).astype(np.float64)
    if vec.size < dim:
        pad = np.zeros(dim - vec.size, dtype=np.float64)
        vec = np.concatenate([vec, pad])
    elif vec.size > dim:
        vec = vec[:dim]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return [float(x) for x in vec.tolist()]


async def embed_asset(request: EmbedAssetRequest, settings: Settings | None = None) -> EmbedAssetResponse:
    settings = settings or get_settings()
    dim = request.dim or settings.embedding_dim
    raw = await fetch_image_bytes(request.asset_url, settings.image_ops_timeout_seconds)
    image = Image.open(io.BytesIO(raw))
    embedding = _image_histogram_embedding(image, dim)
    return EmbedAssetResponse(embedding=embedding, dim=dim, asset_url=request.asset_url)


async def train_avatar_identity(
    request: TrainAvatarIdentityRequest,
    settings: Settings | None = None,
) -> TrainAvatarIdentityResponse:
    settings = settings or get_settings()
    digests: list[str] = []
    for url in request.reference_asset_urls:
        raw = await fetch_image_bytes(url, settings.image_ops_timeout_seconds)
        digests.append(hashlib.sha256(raw).hexdigest()[:12])
    joined = hashlib.sha256("|".join(digests).encode("utf-8")).hexdigest()[:24]
    return TrainAvatarIdentityResponse(identity_profile_ref=f"identity://{joined}")
