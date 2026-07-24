# app/schemas/dashboard.py
"""Response schemas for the Manager Dashboard API.

From spec §8.6 — all dashboard endpoint payloads.
From §21.4 Flow 4 — Manager Dashboard Data Load response shapes.
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# --- GET /dashboard/overview ---

class DashboardOverview(BaseModel):
    """Aggregated summary statistics for the manager dashboard.
    Cached in Redis with 5 min TTL per §5.2 / §21.4 step 1."""
    total_employees: int
    active_learners: int
    avg_mastery_level: float = Field(..., description="Average mastery 0-5 across team")
    avg_mastery_score: float = Field(..., description="Average current_score 0-100")
    total_competencies: int
    skills_mastered_count: int = Field(..., description="States with mastery_level >= 4")
    recent_upgrades_30d: int
    pending_reviews_count: int
    avg_engagement_score: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- GET /dashboard/team-progress ---

class EmployeeSkillProgress(BaseModel):
    """One row in the team progress matrix: employee × skill."""
    employee_id: uuid.UUID
    employee_name: str
    employee_email: str
    skill_id: uuid.UUID
    skill_name: str
    competency_id: uuid.UUID
    competency_name: str
    current_score: float
    mastery_level: int = Field(..., ge=0, le=5)
    mastery_confidence: float
    target_mastery: float = Field(..., description="Skill mastery_threshold from skills table")
    sessions_count: int
    last_assessed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TeamProgressResponse(BaseModel):
    """Paginated team progress matrix — §21.4 step 2."""
    items: list[EmployeeSkillProgress]
    total: int
    skip: int
    limit: int
    has_more: bool


# --- GET /dashboard/skill-gaps ---

class SkillGapItem(BaseModel):
    """A skill where current mastery is below target, sorted by gap severity."""
    employee_id: uuid.UUID
    employee_name: str
    skill_id: uuid.UUID
    skill_name: str
    competency_name: str
    current_mastery_level: int
    target_mastery: float
    gap_severity: float = Field(
        ..., description="target_mastery - (current_mastery_level / 5.0); higher = worse"
    )
    current_score: float
    sessions_count: int
    last_assessed_at: Optional[datetime] = None


class SkillGapsResponse(BaseModel):
    """Skill gaps sorted by gap severity descending — §21.4 step 4."""
    items: list[SkillGapItem]
    total: int
    skip: int
    limit: int


# --- GET /dashboard/recent-mastery ---

class RecentMasteryItem(BaseModel):
    """A mastery upgrade that occurred in the last 30 days."""
    employee_id: uuid.UUID
    employee_name: str
    skill_id: uuid.UUID
    skill_name: str
    old_level: Optional[int]
    new_level: int
    decision: str
    confidence: Optional[float]
    evidence_summary: Optional[str]
    decided_by: str
    created_at: datetime


class RecentMasteryResponse(BaseModel):
    items: list[RecentMasteryItem]
    total: int


# --- GET /dashboard/pending-reviews ---

class PendingReviewItem(BaseModel):
    """A competency with status = 'under_review' awaiting manager validation."""
    competency_id: uuid.UUID
    competency_name: str
    description: Optional[str]
    status: str
    created_by: uuid.UUID
    creator_name: str
    skill_count: int
    decomp_confidence: Optional[float]
    created_at: datetime
    updated_at: Optional[datetime] = None


class PendingReviewsResponse(BaseModel):
    items: list[PendingReviewItem]
    total: int


# --- POST /dashboard/mastery-override ---

class MasteryOverrideRequest(BaseModel):
    """Manager overrides a mastery decision — creates MasteryHistory record
    with decided_by = 'manager_override' per spec §8.6."""
    employee_id: uuid.UUID
    skill_id: uuid.UUID
    new_mastery_level: int = Field(..., ge=0, le=5)
    override_reason: str = Field(..., min_length=10, max_length=1000)


class MasteryOverrideResponse(BaseModel):
    """Confirmation of mastery override with audit trail."""
    history_id: uuid.UUID
    employee_id: uuid.UUID
    skill_id: uuid.UUID
    old_level: int
    new_level: int
    decision: str
    decided_by: str = "manager_override"
    override_reason: str
    overridden_by: uuid.UUID = Field(..., description="Manager user ID who performed the override")
    created_at: datetime
