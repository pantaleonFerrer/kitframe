from __future__ import annotations

import asyncio
import io
import logging
import random
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from kitframe.errors import AppError, ErrorCode
from kitframe.providers.image.base import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from kitframe.settings import Settings

logger = logging.getLogger("kitframe.bfl")

ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (2000, 2000),
    "4:5": (1728, 2160),
    "3:4": (1728, 2304),
    "2:3": (1632, 2448),
    "9:16": (1440, 2560),
    "16:9": (2560, 1440),
}

BFL_EU_HOST = "api.eu.bfl.ai"


class BFLImageProvider:
    key = "bfl"
    max_reference_images = 8

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.eu.bfl.ai/v1",
        model: str = "flux-2-pro",
        safety_tolerance: int = 2,
        output_format: str = "png",
        price_per_image_eur: Decimal = Decimal("0.06"),
        enforce_eu_host: bool = False,
    ) -> None:
        if enforce_eu_host:
            host = urlparse(base_url).hostname or ""
            if host != BFL_EU_HOST:
                raise RuntimeError(
                    f"BFL host must be {BFL_EU_HOST} in staging/production, got {host!r}"
                )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.safety_tolerance = safety_tolerance
        self.output_format = output_format
        self.price_per_image_eur = price_per_image_eur

    def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        return asyncio.run(self.generate_async(req))

    async def generate_async(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        start = time.perf_counter()
        width, height = ASPECT_SIZES[req.aspect_ratio]
        refs = _ordered_refs(req)
        if len(refs) > self.max_reference_images:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"At most {self.max_reference_images} reference images",
                status_code=422,
            )
        base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)
        sem = asyncio.Semaphore(4)
        async with httpx.AsyncClient(timeout=130.0) as client:
            tasks = [
                self._one_variant(client, sem, req.final_prompt, refs, width, height, base_seed + i)
                for i in range(req.variant_count)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        images: list[GeneratedImage] = []
        first_error: Exception | None = None
        for r in results:
            if isinstance(r, Exception):
                if first_error is None:
                    first_error = r
                logger.warning("bfl_variant_failed", exc_info=r)
                continue
            images.append(r)

        if not images:
            if isinstance(first_error, AppError):
                raise first_error
            raise AppError(
                ErrorCode.PROVIDER_ERROR,
                str(first_error or "All BFL variants failed"),
                status_code=502,
            )

        latency_ms = int((time.perf_counter() - start) * 1000)
        return ImageGenerationResult(
            images=images,
            provider=self.key,
            provider_model=self.model,
            cost_eur=self.price_per_image_eur * len(images),
            latency_ms=latency_ms,
        )

    async def _one_variant(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        prompt: str,
        refs: list[str],
        width: int,
        height: int,
        seed: int,
    ) -> GeneratedImage:
        async with sem:
            payload: dict[str, Any] = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "seed": seed,
                "output_format": self.output_format,
                "safety_tolerance": self.safety_tolerance,
            }
            for i, url in enumerate(refs):
                key = "input_image" if i == 0 else f"input_image_{i + 1}"
                payload[key] = url

            submit = await self._request_with_retries(
                client,
                "POST",
                f"{self.base_url}/{self.model}",
                json=payload,
            )
            data = submit.json()
            polling_url = data.get("polling_url")
            if not polling_url:
                raise AppError(ErrorCode.PROVIDER_ERROR, "BFL missing polling_url", status_code=502)

            sample_url = await self._poll_ready(client, polling_url)
            img_resp = await client.get(sample_url)
            img_resp.raise_for_status()
            content = img_resp.content
            img = Image.open(io.BytesIO(content))
            mime = "image/png" if self.output_format == "png" else "image/jpeg"
            return GeneratedImage(
                content=content,
                mime_type=mime,  # type: ignore[arg-type]
                width=img.width,
                height=img.height,
            )

    async def _poll_ready(self, client: httpx.AsyncClient, polling_url: str) -> str:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            resp = await client.get(polling_url, headers={"x-key": self.api_key})
            resp.raise_for_status()
            body = resp.json()
            status = str(body.get("status") or "")
            if status == "Ready":
                sample = (body.get("result") or {}).get("sample")
                if not sample:
                    raise AppError(ErrorCode.PROVIDER_ERROR, "BFL Ready without sample", status_code=502)
                return str(sample)
            if "Moderated" in status:
                raise AppError(
                    ErrorCode.PROVIDER_MODERATED,
                    "Provider moderated the image",
                    status_code=422,
                    details={"status": status},
                )
            if status in ("Error", "Failed", "Task not found") or status.startswith("Error"):
                raise AppError(
                    ErrorCode.PROVIDER_ERROR,
                    f"BFL status {status}",
                    status_code=502,
                    details={"status": status, "detail": body},
                )
            await asyncio.sleep(1)
        raise AppError(ErrorCode.PROVIDER_ERROR, "BFL polling timeout", status_code=502)

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["x-key"] = self.api_key
        delays_5xx = [2.0, 4.0]
        delays_429 = [1.0, 2.0, 4.0]
        attempt_5xx = 0
        attempt_429 = 0
        while True:
            try:
                resp = await client.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                if attempt_5xx >= len(delays_5xx):
                    raise AppError(ErrorCode.PROVIDER_ERROR, str(exc), status_code=502) from exc
                await asyncio.sleep(delays_5xx[attempt_5xx])
                attempt_5xx += 1
                continue
            if resp.status_code == 402:
                raise AppError(
                    ErrorCode.PROVIDER_ERROR,
                    "BFL out of credits",
                    status_code=502,
                    details={"code": "bfl_out_of_credits"},
                )
            if resp.status_code == 429:
                if attempt_429 >= len(delays_429):
                    raise AppError(ErrorCode.PROVIDER_ERROR, "BFL rate limited", status_code=502)
                await asyncio.sleep(delays_429[attempt_429])
                attempt_429 += 1
                continue
            if resp.status_code >= 500:
                if attempt_5xx >= len(delays_5xx):
                    raise AppError(
                        ErrorCode.PROVIDER_ERROR,
                        f"BFL HTTP {resp.status_code}",
                        status_code=502,
                    )
                await asyncio.sleep(delays_5xx[attempt_5xx])
                attempt_5xx += 1
                continue
            if resp.status_code >= 400:
                raise AppError(
                    ErrorCode.PROVIDER_ERROR,
                    f"BFL HTTP {resp.status_code}: {resp.text[:300]}",
                    status_code=502,
                )
            return resp


def _ordered_refs(req: ImageGenerationRequest) -> list[str]:
    refs = [str(u) for u in req.garment_image_urls]
    refs.extend(str(u) for u in req.model_image_urls)
    if req.pose_image_url:
        refs.append(str(req.pose_image_url))
    refs.extend(str(u) for u in req.style_image_urls)
    return refs


def bfl_from_settings(settings: Settings, image_config: dict[str, Any] | None = None) -> BFLImageProvider:
    cfg = image_config or {}
    return BFLImageProvider(
        api_key=settings.bfl_api_key,
        base_url=settings.bfl_api_base_url,
        model=str(cfg.get("model") or settings.image_provider_model or "flux-2-pro"),
        safety_tolerance=int(cfg.get("safety_tolerance", 2)),
        output_format=str(cfg.get("output_format", "png")),
        price_per_image_eur=Decimal(str(cfg.get("price_per_image_eur", "0.06"))),
        enforce_eu_host=settings.is_prod_like,
    )
