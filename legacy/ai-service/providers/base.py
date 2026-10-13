from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class GenerationPrompt(BaseModel):
    garment_asset_url: str = ""
    avatar_identity_ref: str | None = None
    pose_skeleton_url: str | None = None
    scene_description: str = ""
    output_type: str = Field(default="image", pattern="^(image|video)$")


class GeneratedAsset(BaseModel):
    url: str
    provider: str
    cost_usd: float | None = None
    latency_ms: int = 0


class GenerationProvider(Protocol):
    key: str

    def generate(self, prompt: GenerationPrompt) -> GeneratedAsset: ...

    def supports(self, output_type: str) -> bool: ...


class GenerateImageRequest(BaseModel):
    provider: str | None = None
    prompt: GenerationPrompt
    reference_assets: list[str] = Field(default_factory=list)
    avatar_identity_ref: str | None = None
    pose_skeleton_url: str | None = None


class GenerateImageResponse(BaseModel):
    generated_url: str
    provider_used: str
    cost_usd: float | None = None
    latency_ms: int


def resolve_provider_key(requested: str | None, configured: str, providers: dict[str, Any]) -> str:
    key = requested or configured
    if key not in providers:
        if "mock" in providers:
            return "mock"
        raise KeyError(key)
    return key
