#!/usr/bin/env python3
"""FLUX.2 spike helper (§24). Compares flux-2-pro vs flux-2-max on the EU endpoint.

Usage (staging / local with real keys):
  BFL_API_KEY=... python scripts/spike_flux2.py --garment-url https://... --prompt "..."

Never run against production garments in CI. Results go to docs/spike-flux2-results.md (manual).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from kitframe.providers.image.base import ImageGenerationRequest  # noqa: E402
from kitframe.providers.image.bfl import BFLImageProvider  # noqa: E402
from kitframe.settings import Settings  # noqa: E402


async def run(model: str, garment_url: str, prompt: str, aspect: str) -> None:
    settings = Settings()
    provider = BFLImageProvider(
        api_key=settings.bfl_api_key,
        base_url=settings.bfl_api_base_url,
        model=model,
        enforce_eu_host=settings.is_prod_like,
    )
    req = ImageGenerationRequest(
        final_prompt=prompt,
        garment_image_urls=[garment_url],
        model_image_urls=[],
        style_image_urls=[],
        aspect_ratio=aspect,  # type: ignore[arg-type]
        variant_count=1,
        seed=12345,
    )
    result = await provider.generate_async(req)
    out = Path(f"spike-{model.replace('/', '-')}.png")
    out.write_bytes(result.images[0].content)
    print(f"{model}: {result.images[0].width}x{result.images[0].height} -> {out} ({result.latency_ms} ms)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--garment-url", required=True)
    p.add_argument("--prompt", default="Photorealistic e-commerce front view, studio grey background")
    p.add_argument("--aspect", default="1:1")
    p.add_argument("--models", default="flux-2-pro,flux-2-max")
    args = p.parse_args()
    for model in args.models.split(","):
        asyncio.run(run(model.strip(), args.garment_url, args.prompt, args.aspect))


if __name__ == "__main__":
    main()
