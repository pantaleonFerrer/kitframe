from __future__ import annotations

from typing import Any, Protocol

from kitframe.providers.image.bfl import BFLImageProvider, bfl_from_settings
from kitframe.providers.image.fake import FakeImageProvider
from kitframe.providers.llm.fake import FakeLLMClient
from kitframe.providers.llm.mistral import MistralLLMClient, mistral_from_settings
from kitframe.settings import Settings


class ImageProviderProto(Protocol):
    key: str
    max_reference_images: int


def get_image_provider(
    settings: Settings,
    image_config: dict[str, Any] | None = None,
) -> FakeImageProvider | BFLImageProvider:
    cfg = image_config or {}
    key = str(cfg.get("provider") or settings.image_provider)
    if key == "fake":
        if settings.is_prod_like:
            raise RuntimeError("fake image provider not allowed")
        return FakeImageProvider()
    if key == "bfl":
        if not settings.bfl_api_key and settings.is_prod_like:
            raise RuntimeError("BFL_API_KEY required")
        return bfl_from_settings(settings, cfg)
    raise RuntimeError(f"Unknown image provider: {key}")


def get_llm_client(
    settings: Settings,
    llm_config: dict[str, Any] | None = None,
) -> FakeLLMClient | MistralLLMClient:
    cfg = llm_config or {}
    key = str(cfg.get("provider") or settings.llm_provider)
    if key == "fake":
        if settings.is_prod_like:
            raise RuntimeError("fake llm provider not allowed")
        return FakeLLMClient()
    if key == "mistral":
        if not settings.mistral_api_key and settings.is_prod_like:
            raise RuntimeError("MISTRAL_API_KEY required")
        return mistral_from_settings(settings, cfg)
    raise RuntimeError(f"Unknown llm provider: {key}")
