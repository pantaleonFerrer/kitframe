from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, HttpUrl


class ImageGenerationRequest(BaseModel):
    final_prompt: str
    garment_image_urls: list[HttpUrl]
    model_image_urls: list[HttpUrl]
    pose_image_url: HttpUrl | None = None
    style_image_urls: list[HttpUrl]
    aspect_ratio: Literal["1:1", "4:5", "3:4", "2:3", "9:16", "16:9"]
    variant_count: int
    seed: int | None = None


class GeneratedImage(BaseModel):
    content: bytes
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    width: int
    height: int


class ImageGenerationResult(BaseModel):
    images: list[GeneratedImage]
    provider: str
    provider_model: str
    cost_eur: Decimal | None
    latency_ms: int


class ImageProvider(Protocol):
    key: str
    max_reference_images: int

    def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
