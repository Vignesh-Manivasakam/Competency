# app/schemas/assessment.py
from pydantic import BaseModel, Field, UUID4
from typing import Optional
from datetime import datetime
from enum import Enum


class AssessmentMode(str, Enum):
    QUIZ = "quiz"
    CONVERSATIONAL = "conversational"
    SCENARIO = "scenario"
    BASELINE = "baseline"


class DimensionScores(BaseModel):
    accuracy: float = Field(..., ge=0, le=100)
    application: float = Field(..., ge=0, le=100)
    reasoning: float = Field(..., ge=0, le=100)
    consistency: float = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0, le=100)


class Misconception(BaseModel):
    pattern: str
    severity: str = "medium"  # low, medium, high
    explanation: str


class ScoringOutput(BaseModel):
    """Structured output schema for GPT-4o evaluation."""
    dimension_scores: DimensionScores
    composite_score: float = Field(..., ge=0, le=100)
    confidence_signal: float = Field(..., ge=0, le=1.0)
    misconceptions: list[Misconception] = Field(default_factory=list)
    feedback_points: list[str] = Field(default_factory=list)
    evaluation_rationale: str


class AssessmentResultOut(BaseModel):
    id: UUID4
    session_id: UUID4
    composite_score: float
    dimension_scores: DimensionScores
    misconceptions: list[dict]
    feedback_points: list[str]
    created_at: datetime

    class Config:
        from_attributes = True
