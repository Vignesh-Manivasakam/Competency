# app/schemas/session.py
"""Pydantic schemas for session and employee API endpoints.

From §7 — all schemas listed in the spec's Pydantic Models section.
"""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, UUID4


# --- Employee Schemas ---

class EmployeeCreateRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str
    job_title: Optional[str] = None
    department: Optional[str] = None


class EmployeeOut(BaseModel):
    id: UUID4
    email: str
    full_name: str
    role: str
    job_title: Optional[str] = None
    department: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EmployeeAssignRequest(BaseModel):
    """§21.2 Step 1: Assign employee to a competency version."""
    competency_id: UUID4
    competency_version: Optional[str] = None  # e.g. "1.0"; defaults to latest


class BaselineAssessmentRequest(BaseModel):
    """§21.2 Step 2: Trigger baseline assessment session."""
    competency_id: UUID4


class BaselineAssessmentResponse(BaseModel):
    session_id: UUID4
    ws_url: str  # /api/v1/sessions/{id}/ws
    message: str = "Baseline assessment session created. Connect via WebSocket."


# --- Session Schemas (§7) ---

class SessionCreateRequest(BaseModel):
    employee_id: UUID4
    skill_id: UUID4
    session_type: str = Field(
        default="learning",
        pattern="^(baseline|learning|review)$",
    )


class SessionOut(BaseModel):
    id: UUID4
    employee_id: UUID4
    skill_id: UUID4
    competency_id: UUID4
    status: str
    session_type: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    interaction_count: int = 0
    final_score: Optional[float] = None
    mastery_reached: bool = False

    class Config:
        from_attributes = True


class SessionInteractRequest(BaseModel):
    """HTTP polling fallback for WebSocket — §8.5."""
    session_id: UUID4
    employee_response: str
    response_latency_ms: Optional[int] = None


class SessionInteractResponse(BaseModel):
    session_id: UUID4
    tutor_message: str
    next_action: str
    current_score: Optional[float] = None
    interaction_count: int
    mastery_level: Optional[int] = None
    session_complete: bool = False
    feedback_points: list[str] = Field(default_factory=list)


class TranscriptEntry(BaseModel):
    role: str  # "tutor" | "employee"
    content: str
    timestamp: Optional[datetime] = None


class TranscriptOut(BaseModel):
    session_id: UUID4
    entries: list[TranscriptEntry]
    total_entries: int


# --- Learning State Schemas (§7) ---

class LearningStateOut(BaseModel):
    employee_id: UUID4
    skill_id: UUID4
    current_score: float
    mastery_level: int
    mastery_confidence: float
    knowledge_gaps: Any = Field(default_factory=list)
    total_interactions: int
    last_assessed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SkillMatrixEntry(BaseModel):
    skill_id: UUID4
    skill_name: str
    mastery_level: int
    current_score: float
    last_assessed_at: Optional[datetime] = None


class CompetencyMatrixOut(BaseModel):
    employee_id: UUID4
    competency_id: UUID4
    competency_name: str
    skills: list[SkillMatrixEntry]
    overall_progress_pct: float


# --- Mastery Schemas (§8.7) ---

class MasteryEvaluateRequest(BaseModel):
    employee_id: UUID4
    skill_id: UUID4


class MasteryDecisionOut(BaseModel):
    employee_id: UUID4
    skill_id: UUID4
    old_level: Optional[int] = None
    new_level: int
    decision: str  # UPGRADE | MAINTAIN | DOWNGRADE
    confidence: Optional[float] = None
    evidence_summary: Optional[str] = None
    decided_by: str = "ai"
    session_id: Optional[UUID4] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Assessment Schemas (§8.7) ---

class AssessmentOut(BaseModel):
    id: UUID4
    session_id: UUID4
    employee_id: UUID4
    skill_id: UUID4
    assessment_mode: Optional[str] = None
    prompt_text: str
    response_text: str
    response_latency_ms: Optional[int] = None
    composite_score: float
    score_accuracy: Optional[float] = None
    score_application: Optional[float] = None
    score_reasoning: Optional[float] = None
    score_consistency: Optional[float] = None
    score_confidence: Optional[float] = None
    misconceptions: list = Field(default_factory=list)
    feedback_points: list = Field(default_factory=list)
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Pagination ---

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
