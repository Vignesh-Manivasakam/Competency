import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index, text,
)
from pgvector.sqlalchemy import Vector

class LearningSession(SQLModel, table=True):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','completed','timed_out')",
            name="ck_ls_status",
        ),
        CheckConstraint(
            "session_type IN ('baseline','learning','review')",
            name="ck_ls_type",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    employee_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    competency_id: uuid.UUID = Field(foreign_key="competencies.id", nullable=False)
    status: str = Field(default="active", max_length=50)
    session_type: str = Field(default="learning", max_length=50)
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    ended_at: Optional[datetime] = Field(default=None)
    interaction_count: int = Field(default=0)
    final_score: Optional[float] = Field(default=None)
    mastery_reached: bool = Field(default=False)
    path_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class ContentItem(SQLModel, table=True):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('explanation','scenario','quiz','dialogue')",
            name="ck_ci_type",
        ),
        Index("idx_content_skill", "skill_id", "content_type", "difficulty_level"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    content_type: Optional[str] = Field(default=None, max_length=50)
    difficulty_level: Optional[int] = Field(default=None)
    content_body: str = Field(nullable=False)
    interaction_prompts: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    expected_schema: Optional[dict] = Field(
        default={},
        sa_column=Column(JSON, server_default="'{}'"),
    )
    quality_score: Optional[float] = Field(default=None)
    times_used: int = Field(default=0)
    avg_score_lift: Optional[float] = Field(default=None)
    llm_model_used: Optional[str] = Field(default=None, max_length=100)
    # pgvector embedding column — 1536 dimensions (text-embedding-3-small)
    embedding: Optional[list[float]] = Field(
        default=None,
        sa_column=Column(Vector(1536)),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
