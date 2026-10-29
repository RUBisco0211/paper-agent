"""Image support is read from the model card, not guessed per provider."""

from types import SimpleNamespace

from app.agent.catalog import ModelOption, ProviderOption, _supports_vision
from app.sessions.schemas import to_llm_catalog


def test_model_card_with_image_inputs_is_vision_capable():
    card = SimpleNamespace(input_types=["text/plain", "image/png"])

    assert _supports_vision(card) is True


def test_model_card_with_text_only_inputs_is_not_vision_capable():
    card = SimpleNamespace(input_types=["text/plain", "application/x-thinking"])

    assert _supports_vision(card) is False


def test_llm_catalog_reports_vision_capability_to_the_client():
    providers = (
        ProviderOption(
            "dashscope",
            "阿里云百炼",
            (
                ModelOption("vision-model", "Vision", 1000, (), True),
                ModelOption("text-model", "Text", 1000, (), False),
            ),
        ),
    )

    catalog = to_llm_catalog(providers)

    flags = {model.id: model.supports_vision for model in catalog.providers[0].models}
    assert flags == {"vision-model": True, "text-model": False}
