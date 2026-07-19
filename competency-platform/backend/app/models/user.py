import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, JSON, CheckConstraint, Index, text

class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','manager','employee')", name="ck_users_role"),
        Index("idx_users_tenant", "tenant_id"),
        Index("idx_users_role", "role"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    email: str = Field(max_length=255, unique=True, nullable=False)
    hashed_password: str = Field(nullable=False)
    full_name: str = Field(max_length=255, nullable=False)
    role: str = Field(max_length=50, nullable=False)  # admin | manager | employee
    job_title: Optional[str] = Field(default=None, max_length=255)
    department: Optional[str] = Field(default=None, max_length=255)
    metadata_: Optional[dict] = Field(
        default={},
        sa_column=Column("metadata", JSON, server_default="'{}'"),
    )
    is_active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
