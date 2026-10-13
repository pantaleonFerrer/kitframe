from __future__ import annotations

import io
import time
from decimal import Decimal

from PIL import Image, ImageDraw

from kitframe.providers.image.base import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from kitframe.providers.image.bfl import ASPECT_SIZES


class FakeImageProvider:
    key = "fake"
    max_reference_images = 8

    def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        start = time.perf_counter()
        width, height = ASPECT_SIZES.get(req.aspect_ratio, (1024, 1024))
        images: list[GeneratedImage] = []
        for i in range(req.variant_count):
            img = Image.new("RGB", (width, height), color=(125, 26, 29))
            draw = ImageDraw.Draw(img)
            margin = min(width, height) // 12
            draw.rectangle(
                (margin, margin, width - margin, height - margin),
                outline=(212, 193, 172),
                width=8,
            )
            draw.text((margin + 40, height // 2), f"Kitframe fake {i + 1}", fill=(255, 255, 255))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            images.append(
                GeneratedImage(
                    content=buf.getvalue(),
                    mime_type="image/png",
                    width=width,
                    height=height,
                )
            )
        return ImageGenerationResult(
            images=images,
            provider=self.key,
            provider_model="fake-v1",
            cost_eur=Decimal(0),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
