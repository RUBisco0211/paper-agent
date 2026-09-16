from collections.abc import Generator
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy import DateTime, Uuid, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base shared by every domain module."""


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.database_echo,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SessionFactory = sessionmaker[Session]


def get_session() -> Generator[Session]:
    with SessionLocal() as session:
        yield session


def get_session_factory() -> SessionFactory:
    """Session factory for work that outlives the request scope."""
    return SessionLocal


SessionDep = Annotated[Session, Depends(get_session)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
