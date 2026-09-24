"""Read-only LLM provider and model catalog backed by AgentScope model cards."""

from dataclasses import dataclass
from functools import lru_cache

from agentscope.model import (
    AnthropicChatModel,
    DashScopeChatModel,
    DeepSeekChatModel,
    MoonshotChatModel,
    OpenAIChatModel,
    XAIChatModel,
)

from ..platform.config import settings
from ..platform.errors import ValidationError
from ..sessions.ports import LlmConfig


@dataclass(frozen=True, slots=True)
class ModelOption:
    id: str
    label: str
    context_size: int | None
    reasoning_efforts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderOption:
    id: str
    label: str
    models: tuple[ModelOption, ...]


PROVIDERS = {
    "anthropic": ("Anthropic", AnthropicChatModel),
    "dashscope": ("阿里云百炼", DashScopeChatModel),
    "deepseek": ("DeepSeek", DeepSeekChatModel),
    "moonshot": ("Moonshot", MoonshotChatModel),
    "openai": ("OpenAI", OpenAIChatModel),
    "xai": ("xAI", XAIChatModel),
}


@lru_cache(maxsize=1)
def model_catalog() -> tuple[ProviderOption, ...]:
    """Return active AgentScope model cards for enabled native providers."""
    providers: list[ProviderOption] = []
    for provider_id in settings.llm_providers:
        spec = PROVIDERS.get(provider_id)
        if spec is None:
            continue
        label, model_class = spec
        models = tuple(
            ModelOption(
                id=card.name,
                label=card.label,
                context_size=card.context_size,
                reasoning_efforts=_reasoning_efforts(card.parameter_schema),
            )
            for card in model_class.list_models()
            if card.status == "active"
        )
        providers.append(ProviderOption(provider_id, label, models))
    return tuple(providers)


def model_is_available(provider: str, model: str) -> bool:
    return any(
        item.id == provider and any(option.id == model for option in item.models)
        for item in model_catalog()
    )


def reasoning_effort_is_available(
    provider: str,
    model: str,
    reasoning_effort: str | None,
) -> bool:
    if reasoning_effort is None:
        return True
    return any(
        item.id == provider
        and any(
            option.id == model and reasoning_effort in option.reasoning_efforts
            for option in item.models
        )
        for item in model_catalog()
    )


def _reasoning_efforts(schema: dict | None) -> tuple[str, ...]:
    """Read the provider-specific effort enum from an AgentScope Model Card."""
    effort = (schema or {}).get("properties", {}).get("reasoning_effort", {})
    for variant in effort.get("anyOf", [effort]):
        values = variant.get("enum")
        if values:
            return tuple(str(value) for value in values)
    return ()


def validate_llm_config(
    *,
    provider: str,
    model: str,
    api_key: str,
    reasoning_effort: str | None = None,
) -> LlmConfig:
    """Accept only a provider/model pair published by the model catalog."""
    provider = provider.strip().lower()
    model = model.strip()
    api_key = api_key.strip()
    if not model_is_available(provider, model):
        raise ValidationError("请选择支持的模型")
    if not api_key:
        raise ValidationError("缺少 API Key")
    if not reasoning_effort_is_available(provider, model, reasoning_effort):
        raise ValidationError("所选模型不支持该思考强度")
    return LlmConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
    )
