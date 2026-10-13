from __future__ import annotations

import io
from decimal import Decimal
from urllib.parse import urlparse

import httpx
import pytest
import respx
from PIL import Image

from kitframe.extraction.schema import (
    alt_text_schema,
    assert_strict_schema,
    copy_schema,
    enforce_strict_schema,
    taxonomy_extraction_schema,
)
from kitframe.providers.image.bfl import ASPECT_SIZES, BFLImageProvider
from kitframe.providers.image.base import ImageGenerationRequest
from kitframe.providers.llm.mistral import MistralLLMClient
from kitframe.qc.resolution import check_resolution
from kitframe.settings import Settings
from kitframe.studio.prompt import compose_final_prompt, format_image_refs


def _png_bytes(w: int = 64, h: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_format_image_refs() -> None:
    assert format_image_refs(1, 1) == "image 1"
    assert format_image_refs(1, 2) == "image 1 and image 2"
    assert format_image_refs(3, 3) == "images 3 to 5"


def test_prompt_numbered_refs_snapshot() -> None:
    text = compose_final_prompt(
        generation_rules="RULES",
        prompt="estudio fondo gris",
        restrictions="sin gafas",
        aspect_ratio="4:5",
        shot_type="model_front",
        n_garment=2,
        n_model=3,
        n_pose=1,
        n_style=1,
    )
    assert "image 1 and image 2 show the real garment" in text
    assert "images 3 to 5" in text
    assert "image 6" in text
    assert "image 7" in text
    assert "full-body front view of the model wearing the garment" in text
    assert "aspect ratio 4:5" in text


def test_resolution_generated_threshold() -> None:
    real = check_resolution(1600, 1600, 2000, origin="real_photo", min_short_side_px_generated=1440)
    assert real["result"] == "fail"
    gen = check_resolution(1600, 1600, 2000, origin="generated", min_short_side_px_generated=1440)
    assert gen["result"] == "pass"
    assert gen["min_short_side_px"] == 1440


def test_strict_schemas() -> None:
    for schema in (
        copy_schema(),
        alt_text_schema(),
        taxonomy_extraction_schema(
            {
                "fields": [
                    {"key": "composition", "type": "string"},
                    {"key": "garment_category", "type": "enum"},
                ]
            }
        ),
    ):
        assert_strict_schema(schema)
        enforced = enforce_strict_schema(schema)
        assert_strict_schema(enforced)


def test_settings_eu_host_guard() -> None:
    with pytest.raises(RuntimeError, match="api.eu.bfl.ai"):
        Settings(
            app_env="production",
            image_provider="bfl",
            llm_provider="mistral",
            bfl_api_key="k",
            mistral_api_key="m",
            bfl_api_base_url="https://api.bfl.ai/v1",
            jwt_secret="local-dev-jwt-secret-change-me-now!!",
        ).validate_providers()


def test_settings_fake_blocked_in_prod() -> None:
    with pytest.raises(RuntimeError, match="fake"):
        Settings(
            app_env="staging",
            image_provider="fake",
            llm_provider="fake",
            jwt_secret="local-dev-jwt-secret-change-me-now!!",
        ).validate_providers()


def test_aspect_sizes_table() -> None:
    assert ASPECT_SIZES["1:1"] == (2000, 2000)
    assert ASPECT_SIZES["4:5"] == (1728, 2160)
    assert ASPECT_SIZES["16:9"] == (2560, 1440)


@respx.mock
@pytest.mark.asyncio
async def test_bfl_ready_flow() -> None:
    png = _png_bytes(128, 128)
    submit = respx.post("https://api.eu.bfl.ai/v1/flux-2-pro").mock(
        return_value=httpx.Response(200, json={"id": "t1", "polling_url": "https://api.eu.bfl.ai/v1/get_result?id=t1"})
    )
    poll = respx.get("https://api.eu.bfl.ai/v1/get_result").mock(
        return_value=httpx.Response(
            200, json={"status": "Ready", "result": {"sample": "https://cdn.example/sample.png"}}
        )
    )
    download = respx.get("https://cdn.example/sample.png").mock(return_value=httpx.Response(200, content=png))

    provider = BFLImageProvider(api_key="test-key", price_per_image_eur=Decimal("0.06"))
    req = ImageGenerationRequest(
        final_prompt="test",
        garment_image_urls=["https://fixture.local/g1.jpg"],
        model_image_urls=[],
        pose_image_url=None,
        style_image_urls=[],
        aspect_ratio="1:1",
        variant_count=1,
        seed=42,
    )
    result = await provider.generate_async(req)
    assert submit.called
    assert poll.called
    assert download.called
    assert result.images[0].width == 128
    assert result.cost_eur == Decimal("0.06")
    assert result.provider == "bfl"


@respx.mock
@pytest.mark.asyncio
async def test_bfl_moderated() -> None:
    respx.post("https://api.eu.bfl.ai/v1/flux-2-pro").mock(
        return_value=httpx.Response(200, json={"id": "t1", "polling_url": "https://api.eu.bfl.ai/v1/get_result?id=t1"})
    )
    respx.get("https://api.eu.bfl.ai/v1/get_result").mock(
        return_value=httpx.Response(200, json={"status": "Content Moderated"})
    )
    provider = BFLImageProvider(api_key="test-key")
    req = ImageGenerationRequest(
        final_prompt="bad",
        garment_image_urls=["https://fixture.local/g1.jpg"],
        model_image_urls=[],
        style_image_urls=[],
        aspect_ratio="1:1",
        variant_count=1,
    )
    from kitframe.errors import AppError, ErrorCode

    with pytest.raises(AppError) as ei:
        await provider.generate_async(req)
    assert ei.value.code == ErrorCode.PROVIDER_MODERATED


@respx.mock
@pytest.mark.asyncio
async def test_bfl_402_credits() -> None:
    respx.post("https://api.eu.bfl.ai/v1/flux-2-pro").mock(return_value=httpx.Response(402, text="no credits"))
    provider = BFLImageProvider(api_key="test-key")
    req = ImageGenerationRequest(
        final_prompt="x",
        garment_image_urls=["https://fixture.local/g1.jpg"],
        model_image_urls=[],
        style_image_urls=[],
        aspect_ratio="1:1",
        variant_count=1,
    )
    from kitframe.errors import AppError, ErrorCode

    with pytest.raises(AppError) as ei:
        await provider.generate_async(req)
    assert ei.value.code == ErrorCode.PROVIDER_ERROR
    assert ei.value.details.get("code") == "bfl_out_of_credits"


def test_bfl_eu_host_enforced() -> None:
    with pytest.raises(RuntimeError, match="api.eu.bfl.ai"):
        BFLImageProvider(
            api_key="k",
            base_url="https://api.us.bfl.ai/v1",
            enforce_eu_host=True,
        )


@respx.mock
@pytest.mark.asyncio
async def test_mistral_strict_json() -> None:
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"es":"a","ca":"b","en":"c"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )
    client = MistralLLMClient(api_key="m")
    out = await client.complete_json_async(
        "sys",
        "user",
        alt_text_schema(),
        schema_name="alt_text",
    )
    assert out == {"es": "a", "ca": "b", "en": "c"}
    assert client.last_usage["prompt_tokens"] == 10


def test_urlparse_eu() -> None:
    assert urlparse("https://api.eu.bfl.ai/v1").hostname == "api.eu.bfl.ai"
