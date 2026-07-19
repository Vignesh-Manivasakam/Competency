import uuid
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID


class UUIDModel(SQLModel):
    """Mixin that adds a UUID primary key."""
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )


class TimestampModel(SQLModel):
    """Mixin that adds created_at and updated_at timestamps."""
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("NOW()"),
            nullable=False,
        ),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("NOW()"),
            onupdate=datetime.utcnow,
            nullable=False,
        ),
    )
