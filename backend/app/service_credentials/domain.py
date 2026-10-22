"""Third-party service credentials the user supplies for their own account.

Each service declares which of its fields are secret: those are encrypted at
rest per user, everything else stays readable so the settings page can show it.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceCredentialSpec:
    """What a service expects, and which of it must never be stored plainly."""

    kind: str
    label: str
    secret_fields: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()


TAVILY = ServiceCredentialSpec(
    kind="tavily",
    label="Tavily",
    secret_fields=("api_key",),
    required_fields=("api_key",),
)

SPECS: dict[str, ServiceCredentialSpec] = {spec.kind: spec for spec in (TAVILY,)}


def spec_for(kind: str) -> ServiceCredentialSpec:
    spec = SPECS.get(kind)
    if spec is None:
        raise ValueError(f"Unknown service credential kind: {kind}")
    return spec
