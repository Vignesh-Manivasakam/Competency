import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index,
    UniqueConstraint, text,
)

class EmployeeLearningState(SQLModel, table=True):
    __tablename__ = "employee_learning_states"
    __table_args__ = (
        CheckConstraint("current_score BETWEEN 0 AND 100", name="ck_els_score"),
        CheckConstraint("mastery_level BETWEEN 0 AND 5", name="ck_els_mastery"),
        UniqueConstraint("employee_id", "skill_id", name="uq_els_employee_skill"),
        Index("idx_els_employee", "employee_id"),
        Index("idx_els_skill", "skill_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    employee_id: uuid.UUID = Field(
        foreign_key="users.id",
        nullable=False,
        ondelete="CASCADE",
    )
    skill_id: uuid.UUID = Field(
        foreign_key="skills.id",
        nullable=False,
        ondelete="CASCADE",
    )
    competency_id: uuid.UUID = Field(foreign_key="competencies.id", nullable=False)
    current_score: float = Field(default=0.0)
    mastery_level: int = Field(default=0)
    mastery_confidence: float = Field(default=0.0)
    knowledge_gaps: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    misconception_map: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    learning_velocity: float = Field(default=0.0)
    engagement_score: float = Field(default=0.0)
    total_interactions: int = Field(default=0)
    sessions_count: int = Field(default=0)
    last_assessed_at: Optional[datetime] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
