from __future__ import annotations

import base64
import hashlib
import io
import time

from PIL import Image, ImageDraw, ImageFont

from providers.base import GeneratedAsset, GenerationPrompt


def _render_mock_image(prompt: GenerationPrompt, digest: str) -> bytes:
    width, height = 768, 1024
    img = Image.new("RGB", (width, height), color=(52, 57, 63))
    draw = ImageDraw.Draw(img)

    draw.rectangle((48, 64, width - 48, height - 64), fill=(125, 26, 29))
    draw.rectangle((72, 96, width - 72, height - 96), fill=(241, 235, 227))

    accent = (212, 193, 172)
    draw.rounded_rectangle((140, 180, width - 140, 520), radius=28, fill=accent)
    draw.ellipse((width // 2 - 90, 240, width // 2 + 90, 420), fill=(52, 57, 63))

    font = ImageFont.load_default()
    title = "Kitframe mock look"
    scene = (prompt.scene_description or "studio").strip()[:72]
    identity = (prompt.avatar_identity_ref or "identity://mock")[-18:]
    pose = "pose" if prompt.pose_skeleton_url else "free pose"
    garment = "garment linked" if prompt.garment_asset_url else "no garment url"

    lines = [
        title,
        scene,
        f"id {identity}",
        pose,
        garment,
        digest[:12],
    ]
    y = 560
    for line in lines:
        draw.text((96, y), line, fill=(52, 57, 63), font=font)
        y += 36

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class MockProvider:
    key = "mock"

    def supports(self, output_type: str) -> bool:
        return output_type in {"image", "video"}

    def generate(self, prompt: GenerationPrompt) -> GeneratedAsset:
        started = time.perf_counter()
        digest = hashlib.sha256(
            "|".join(
                [
                    prompt.garment_asset_url or "",
                    prompt.avatar_identity_ref or "",
                    prompt.pose_skeleton_url or "",
                    prompt.scene_description or "",
                    prompt.output_type,
                ]
            ).encode("utf-8")
        ).hexdigest()[:16]
        if prompt.output_type == "video":
            url = f"mock://generated/{digest}.mp4"
        else:
            raw = _render_mock_image(prompt, digest)
            encoded = base64.b64encode(raw).decode("ascii")
            url = f"data:image/png;base64,{encoded}"
        latency_ms = int((time.perf_counter() - started) * 1000)
        return GeneratedAsset(
            url=url,
            provider=self.key,
            cost_usd=0.0,
            latency_ms=max(latency_ms, 1),
        )
