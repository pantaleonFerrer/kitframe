from providers.base import GenerationPrompt
from providers.mock import MockProvider


def test_mock_provider_is_deterministic():
    provider = MockProvider()
    prompt = GenerationPrompt(
        garment_asset_url="https://example.com/garment.png",
        avatar_identity_ref="identity://abc",
        pose_skeleton_url="https://example.com/pose.png",
        scene_description="studio front view",
        output_type="image",
    )
    first = provider.generate(prompt)
    second = provider.generate(prompt)
    assert first.url == second.url
    assert first.provider == "mock"
    assert first.url.startswith("data:image/png;base64,")
    assert first.cost_usd == 0.0
    assert first.latency_ms >= 1


def test_mock_provider_supports_image_and_video():
    provider = MockProvider()
    assert provider.supports("image") is True
    assert provider.supports("video") is True
    assert provider.supports("audio") is False


def test_mock_provider_changes_with_prompt():
    provider = MockProvider()
    a = provider.generate(
        GenerationPrompt(
            garment_asset_url="https://example.com/a.png",
            scene_description="a",
            output_type="image",
        )
    )
    b = provider.generate(
        GenerationPrompt(
            garment_asset_url="https://example.com/b.png",
            scene_description="b",
            output_type="image",
        )
    )
    assert a.url != b.url
