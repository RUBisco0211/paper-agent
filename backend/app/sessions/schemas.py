from uuid import UUID

from pydantic import BaseModel

from ..agent.catalog import ProviderOption


class LlmModelRead(BaseModel):
    id: str
    label: str
    context_size: int | None = None
    reasoning_efforts: list[str] = []


class LlmProviderRead(BaseModel):
    id: str
    label: str
    models: list[LlmModelRead]


class LlmCatalogResponse(BaseModel):
    providers: list[LlmProviderRead]


def to_llm_catalog(providers: tuple[ProviderOption, ...]) -> LlmCatalogResponse:
    return LlmCatalogResponse(
        providers=[
            LlmProviderRead(
                id=provider.id,
                label=provider.label,
                models=[
                    LlmModelRead(
                        id=model.id,
                        label=model.label,
                        context_size=model.context_size,
                        reasoning_efforts=list(model.reasoning_efforts),
                    )
                    for model in provider.models
                ],
            )
            for provider in providers
        ],
    )


class SessionBindingCreateRequest(BaseModel):
    session_id: UUID
    project_id: UUID | None = None


class SessionBindingRead(BaseModel):
    session_id: UUID
    project_id: UUID | None
    scope: str


class BoundCitationRead(BaseModel):
    citation_id: str
    paper_id: UUID
    title_path: str | None
    snippet: str
    page_start: int | None
    page_end: int | None
    chunk_ids: list[UUID]
