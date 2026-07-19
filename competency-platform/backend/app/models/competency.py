import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index,
    Float, Integer, Text, text, ARRAY, String,
)

class Competency(SQLModel, table=True):
    __tablename__ = "competencies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','under_review','active','deprecated')",
            name="ck_competencies_status",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    tenant_id: uuid.UUID = Field(foreign_key="tenants.id", nullable=False)
    name: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(default=None)
    business_relevance: Optional[str] = Field(default=None)
    target_roles: Optional[list[str]] = Field(
        default=[],
        sa_column=Column(ARRAY(String)),
    )
    version_major: int = Field(default=1)
    version_minor: int = Field(default=0)
    status: str = Field(default="draft", max_length=50)
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    approved_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    approved_at: Optional[datetime] = Field(default=None)
    decomp_confidence: Optional[float] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint("hierarchy_level BETWEEN 1 AND 3", name="ck_skills_hierarchy"),
        CheckConstraint("difficulty_level BETWEEN 1 AND 5", name="ck_skills_difficulty"),
        CheckConstraint(
            "learning_strategy IN ('conceptual','procedural','applied','analytical')",
            name="ck_skills_strategy",
        ),
        Index("idx_skills_competency", "competency_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    competency_id: uuid.UUID = Field(
        foreign_key="competencies.id",
        nullable=False,
        ondelete="CASCADE",
    )
    name: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(default=None)
    hierarchy_level: int = Field(default=1)
    difficulty_level: int = Field(default=1)
    learning_strategy: Optional[str] = Field(default=None, max_length=50)
    mastery_threshold: float = Field(default=0.80)
    eval_dimensions: Optional[dict] = Field(
        default={},
        sa_column=Column(JSON, server_default="'{}'"),
    )
    estimated_minutes: int = Field(default=60)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class SkillEdge(SQLModel, table=True):
    """Skill dependency edges — the DAG structure in PostgreSQL."""
    __tablename__ = "skill_edges"

    prerequisite_id: uuid.UUID = Field(
        foreign_key="skills.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    dependent_id: uuid.UUID = Field(
        foreign_key="skills.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    edge_type: str = Field(default="requires", max_length=50)
    strength: float = Field(default=1.0)
