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
