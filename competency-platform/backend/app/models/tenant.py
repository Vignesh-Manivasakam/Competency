import uuid
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, DateTime, text

class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    name: str = Field(max_length=255, nullable=False)
    slug: str = Field(max_length=100, unique=True, nullable=False)
    settings: Optional[dict] = Field(default={}, sa_column=Column(JSON, server_default="'{}'"))
    created_at: Optional[str] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
