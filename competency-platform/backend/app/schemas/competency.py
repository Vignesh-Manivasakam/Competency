# app/schemas/competency.py
from pydantic import BaseModel, Field, UUID4
from typing import Optional
from enum import Enum
from datetime import datetime


class SkillStrategy(str, Enum):
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    APPLIED = "applied"
    ANALYTICAL = "analytical"


class SkillNodeCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str
    hierarchy_level: int = Field(default=1, ge=1, le=3)
    difficulty_level: int = Field(default=1, ge=1, le=5)
    learning_strategy: SkillStrategy = SkillStrategy.CONCEPTUAL
    estimated_minutes: int = Field(default=60, ge=5, le=480)


class SkillEdgeCreate(BaseModel):
    prerequisite_name: str  # Name-based for LLM output; resolved to UUID later
    dependent_name: str
    strength: float = Field(default=1.0, ge=0.0, le=1.0)


class CompetencyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str
    business_relevance: Optional[str] = None
    target_roles: list[str] = Field(default_factory=list)


class CompetencyDecomposeRequest(BaseModel):
    competency_id: UUID4
    max_depth: int = Field(default=2, ge=1, le=3)
    industry_context: Optional[str] = None


class CompetencyDecomposeResponse(BaseModel):
    competency_id: UUID4
    skill_nodes: list[dict]
    skill_edges: list[dict]
    rationale: str
    confidence_score: float
    requires_manager_review: bool


class CompetencyValidateRequest(BaseModel):
    competency_id: UUID4
    approved_nodes: list[UUID4]
    removed_nodes: list[UUID4] = Field(default_factory=list)
    manager_notes: Optional[str] = None


class CompetencyOut(BaseModel):
    id: UUID4
    name: str
    description: Optional[str]
    status: str
    version_major: int
    version_minor: int
    target_roles: list[str]
    decomp_confidence: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Structured output schema for LLM ---
class DecompositionOutput(BaseModel):
    """Schema for GPT-4o structured output (JSON schema enforcement)."""
    skill_nodes: list[SkillNodeCreate]
    skill_edges: list[SkillEdgeCreate]
    decomposition_rationale: str = Field(
        ..., description="Explanation of why skills were decomposed this way"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence in the decomposition quality (0.0-1.0)"
    )
