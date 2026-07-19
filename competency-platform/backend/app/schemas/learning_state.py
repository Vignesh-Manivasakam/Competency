# app/schemas/learning_state.py
from pydantic import BaseModel, Field, UUID4
from typing import Optional
from datetime import datetime
from enum import IntEnum


class MasteryLevel(IntEnum):
    NOT_STARTED = 0
    AWARENESS = 1
    DEVELOPING = 2
    PROFICIENT = 3
    ADVANCED = 4
    MASTERED = 5


class LearningStateOut(BaseModel):
    employee_id: UUID4
    skill_id: UUID4
    current_score: float
    mastery_level: MasteryLevel
    mastery_confidence: float
    knowledge_gaps: list[dict]
    total_interactions: int
    last_assessed_at: Optional[datetime]

    class Config:
        from_attributes = True


class SkillMatrixEntry(BaseModel):
    skill_id: UUID4
    skill_name: str
    mastery_level: MasteryLevel
    current_score: float
    last_assessed_at: Optional[datetime]


class CompetencyMatrixOut(BaseModel):
    employee_id: UUID4
    competency_id: UUID4
    competency_name: str
    skills: list[SkillMatrixEntry]
    overall_progress_pct: float
