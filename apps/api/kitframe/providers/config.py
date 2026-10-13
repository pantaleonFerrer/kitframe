from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ImageProviderConfig(BaseModel):
    provider: Literal["bfl", "fake"]
    model: str
    safety_tolerance: int = 2
    output_format: Literal["png", "jpeg"] = "png"
    price_per_image_eur: float = Field(default=0.06, ge=0)

    @field_validator("model")
    @classmethod
    def pinned_image_model(cls, value: str, info: ValidationInfo) -> str:
        provider = info.data.get("provider")
        if provider == "bfl" and value not in ("flux-2-pro", "flux-2-max"):
            raise ValueError("BFL model must be flux-2-pro or flux-2-max")
        if "-latest" in value:
            raise ValueError("Pinned model ids only; aliases ending in -latest are not allowed")
        return value


class LLMProviderConfig(BaseModel):
    provider: Literal["mistral", "fake"]
    model: str

    @field_validator("model")
    @classmethod
    def pinned_llm_model(cls, value: str) -> str:
        if "-latest" in value:
            raise ValueError("Pinned model ids only; aliases ending in -latest are not allowed")
        return value


class ProviderConfig(BaseModel):
    image: ImageProviderConfig
    llm: LLMProviderConfig


class QCResolutionConfig(BaseModel):
    min_short_side_px: int = 2000
    min_short_side_px_generated: int = 1440


class QCColorConfig(BaseModel):
    clusters: int = 3
    pass_max_delta_e: float = 3.0
    review_max_delta_e: float = 6.0


class QCCrestConfig(BaseModel):
    pass_min_confidence: float = 0.80
    review_min_confidence: float = 0.55
    position_tolerance: float = 0.05


class QCExtractionConfig(BaseModel):
    confirm_below_confidence: float = 0.85


class QCConfig(BaseModel):
    resolution: QCResolutionConfig = Field(default_factory=QCResolutionConfig)
    color: QCColorConfig = Field(default_factory=QCColorConfig)
    crest: QCCrestConfig = Field(default_factory=QCCrestConfig)
    extraction: QCExtractionConfig = Field(default_factory=QCExtractionConfig)


def validate_provider_config(raw: dict[str, Any]) -> dict[str, Any]:
    return ProviderConfig.model_validate(raw).model_dump()


def validate_qc_config(raw: dict[str, Any]) -> dict[str, Any]:
    return QCConfig.model_validate(raw).model_dump()
