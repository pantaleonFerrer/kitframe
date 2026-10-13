from __future__ import annotations

import time

import httpx

from app.config import get_settings
from providers.base import GeneratedAsset, GenerationPrompt


class FalProvider:
    key = "fal"

    def __init__(self, api_key: str | None = None, model_id: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.fal_key
        self._model_id = model_id if model_id is not None else settings.fal_model_id
        self._client = httpx.Client(timeout=60.0)

    def supports(self, output_type: str) -> bool:
        return output_type == "image"

    def generate(self, prompt: GenerationPrompt) -> GeneratedAsset:
        if not self._api_key:
            raise RuntimeError("FAL_KEY is not configured")
        if not self.supports(prompt.output_type):
            raise ValueError(f"fal does not support output_type={prompt.output_type}")

        started = time.perf_counter()
        text = prompt.scene_description or "product garment photo"
        payload = {
            "prompt": text,
            "image_url": prompt.garment_asset_url,
            "num_images": 1,
        }
        headers = {
            "Authorization": f"Key {self._api_key}",
            "Content-Type": "application/json",
        }
        response = self._client.post(
            f"https://fal.run/{self._model_id}",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        images = data.get("images") or data.get("image") or []
        if isinstance(images, dict):
            url = images.get("url")
        elif isinstance(images, list) and images:
            first = images[0]
            url = first.get("url") if isinstance(first, dict) else str(first)
        else:
            url = data.get("url")
        if not url:
            raise RuntimeError("fal response missing image url")
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost = data.get("cost_usd")
        return GeneratedAsset(
            url=str(url),
            provider=self.key,
            cost_usd=float(cost) if cost is not None else None,
            latency_ms=latency_ms,
        )
