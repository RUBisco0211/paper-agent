from typing import Annotated, Self

from fastapi import Depends, Query
from pydantic import BaseModel


class PageParams:
    """Offset pagination shared by every list endpoint."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PageParamsDep = Annotated[PageParams, Depends()]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int

    @classmethod
    def create(
        cls,
        items: list[T],
        *,
        total: int,
        params: PageParams,
    ) -> Self:
        return cls(
            items=items,
            total=total,
            limit=params.limit,
            offset=params.offset,
        )
