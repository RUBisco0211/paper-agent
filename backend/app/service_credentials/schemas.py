from pydantic import BaseModel, Field


class ServiceCredentialWrite(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    label: str = Field(default="", max_length=128)
    fields: dict[str, str] = Field(default_factory=dict)


class ServiceCredentialRead(BaseModel):
    kind: str
    label: str
    fields: dict[str, str]


class ServiceCredentialListRead(BaseModel):
    items: list[ServiceCredentialRead]
