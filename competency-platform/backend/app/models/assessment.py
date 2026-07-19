import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import (
    Column, DateTime, JSON, CheckConstraint, Index, text,
)

class AssessmentResult(SQLModel, table=True):
    __tablename__ = "assessment_results"
    __table_args__ = (
        CheckConstraint(
            "assessment_mode IN ('quiz','conversational','scenario','baseline')",
            name="ck_ar_mode",
        ),
        Index("idx_ar_employee_skill", "employee_id", "skill_id"),
        Index("idx_ar_session", "session_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    session_id: uuid.UUID = Field(nullable=False)
    employee_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    assessment_mode: Optional[str] = Field(default=None, max_length=50)
    prompt_text: str = Field(nullable=False)
    response_text: str = Field(nullable=False)
    response_latency_ms: Optional[int] = Field(default=None)
    score_accuracy: Optional[float] = Field(default=None)
    score_application: Optional[float] = Field(default=None)
    score_reasoning: Optional[float] = Field(default=None)
    score_consistency: Optional[float] = Field(default=None)
    score_confidence: Optional[float] = Field(default=None)
    composite_score: float = Field(nullable=False)
    misconceptions: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    feedback_points: Optional[list] = Field(
        default=[],
        sa_column=Column(JSON, server_default="'[]'"),
    )
    llm_model_used: Optional[str] = Field(default=None, max_length=100)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )


class MasteryHistory(SQLModel, table=True):
    """Immutable append-only mastery decision log."""
    __tablename__ = "mastery_history"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('UPGRADE','MAINTAIN','DOWNGRADE')",
            name="ck_mh_decision",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    employee_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    skill_id: uuid.UUID = Field(foreign_key="skills.id", nullable=False)
    old_level: Optional[int] = Field(default=None)
    new_level: int = Field(nullable=False)
    decision: Optional[str] = Field(default=None, max_length=20)
    confidence: Optional[float] = Field(default=None)
    evidence_summary: Optional[str] = Field(default=None)
    decided_by: str = Field(default="ai", max_length=50)  # 'ai' or 'manager_override'
    override_reason: Optional[str] = Field(default=None)
    session_id: Optional[uuid.UUID] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
    )
