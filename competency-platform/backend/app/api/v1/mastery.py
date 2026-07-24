# app/api/v1/mastery.py
"""Mastery evaluation and decision endpoints.

§8.7 Mastery and Assessment Routes
POST /mastery/evaluate — Trigger mastery evaluation for employee+skill
GET /mastery/{employee_id}/{skill_id} — Get current mastery decision detail
GET /mastery/{employee_id}/history — All mastery decisions for employee
"""
import uuid
import math
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

from app.api.dependencies import get_current_user, require_role, get_async_session, get_redis
from app.core.errors import PlatformError
from app.models.user import User
from app.models.assessment import AssessmentResult, MasteryHistory
from app.models.learning_state import EmployeeLearningState
from app.agents.learning_state_manager import LearningStateManagerAgent
from app.schemas.session import (
    MasteryEvaluateRequest,
    MasteryDecisionOut,
    PaginatedResponse,
)

logger = structlog.get_logger()

router = APIRouter()


def _validate_mastery_access(employee_id: uuid.UUID, current_user: User):
    """Employees can only view their own mastery; managers/admins can view any."""
    if current_user.role == "employee" and current_user.id != employee_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


# --- POST /mastery/evaluate — Trigger mastery evaluation (§8.7) ---
@router.post("/evaluate", response_model=MasteryDecisionOut)
async def evaluate_mastery(
    body: MasteryEvaluateRequest,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(require_role("manager", "admin")),
):
    """Trigger mastery evaluation for a specific employee+skill (§8.7).

    Invokes the MasteryEvaluationAgent (Plan 14) which:
    1. Loads recent assessments (last 5-10)
    2. Applies hard-coded decision rules
    3. Checks prerequisites in Neo4j
    4. Confirms via LLM
    5. Commits decision via Learning State Manager

    Requires sufficient assessment data (§19.2 INSUFFICIENT_ASSESSMENT_DATA).
    """
    # Validate learning state exists
    result = await db.exec(
        select(EmployeeLearningState).where(
            EmployeeLearningState.employee_id == body.employee_id,
            EmployeeLearningState.skill_id == body.skill_id,
        )
    )
    learning_state = result.first()
    if not learning_state:
        raise HTTPException(
            status_code=404,
            detail="No learning state found for this employee+skill",
        )

    # Check sufficient assessment data (§19.2 INSUFFICIENT_ASSESSMENT_DATA)
    assessment_count_result = await db.exec(
        select(func.count(AssessmentResult.id)).where(
            AssessmentResult.employee_id == body.employee_id,
            AssessmentResult.skill_id == body.skill_id,
        )
    )
    assessment_count = assessment_count_result.one()

    if assessment_count < 3:
        raise PlatformError(
            code="INSUFFICIENT_ASSESSMENT_DATA",
            message=f"Need at least 3 assessments for mastery evaluation (found {assessment_count})",
            detail="Complete more learning sessions before requesting mastery evaluation",
            status_code=422,
        )

    # Load recent assessments for the agent
    assessments_result = await db.exec(
        select(AssessmentResult)
        .where(
            AssessmentResult.employee_id == body.employee_id,
            AssessmentResult.skill_id == body.skill_id,
        )
        .order_by(AssessmentResult.created_at.desc())
        .limit(10)
    )
    recent_assessments = assessments_result.all()

    # Build state dict for MasteryEvaluationAgent (Plan 14)
    from app.agents.mastery_evaluation import MasteryEvaluationAgent
    agent = MasteryEvaluationAgent()

    agent_state = {
        "session_id": "",
        "employee_id": str(body.employee_id),
        "skill_id": str(body.skill_id),
        "session_scores": [a.composite_score for a in recent_assessments],
        "generated_content": {
            "recent_assessments": [
                {
                    "composite_score": a.composite_score,
                    "confidence_signal": a.score_confidence or 0.5,
                    "interaction_count": 1,
                }
                for a in recent_assessments
            ],
            "error_history": [],
            "skill_name": "",
        },
    }

    res_agent = await agent.process(agent_state)
    decision = res_agent.get("mastery_decision", {})

    # Commit via Learning State Manager
    state_mgr = LearningStateManagerAgent(db, redis)
    await state_mgr.commit_mastery_decision(decision)

    # Return the most recent mastery history entry
    latest = await db.exec(
        select(MasteryHistory)
        .where(
            MasteryHistory.employee_id == body.employee_id,
            MasteryHistory.skill_id == body.skill_id,
        )
        .order_by(MasteryHistory.created_at.desc())
        .limit(1)
    )
    history_entry = latest.first()

    if history_entry:
        return MasteryDecisionOut.model_validate(history_entry)

    # Fallback
    return MasteryDecisionOut(
        employee_id=body.employee_id,
        skill_id=body.skill_id,
        old_level=decision.get("old_level"),
        new_level=decision.get("new_mastery_level", 0),
        decision=decision.get("mastery_decision", "MAINTAIN"),
        confidence=decision.get("confidence"),
        evidence_summary=decision.get("evidence_summary"),
    )


# --- GET /mastery/{employee_id}/history — All mastery decisions (§8.7) ---
# Registering /history before /{skill_id} to avoid path collision
@router.get("/{employee_id}/history", response_model=PaginatedResponse)
async def get_mastery_history(
    employee_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    skill_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get all mastery decisions for an employee, paginated (§8.7)."""
    _validate_mastery_access(employee_id, current_user)

    query = select(MasteryHistory).where(
        MasteryHistory.employee_id == employee_id
    )
    count_query = select(func.count(MasteryHistory.id)).where(
        MasteryHistory.employee_id == employee_id
    )

    if skill_id:
        query = query.where(MasteryHistory.skill_id == skill_id)
        count_query = count_query.where(MasteryHistory.skill_id == skill_id)

    total = (await db.exec(count_query)).one()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    offset = (page - 1) * page_size
    query = query.order_by(MasteryHistory.created_at.desc()).offset(offset).limit(page_size)
    result = await db.exec(query)
    entries = result.all()

    return PaginatedResponse(
        items=[MasteryDecisionOut.model_validate(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# --- GET /mastery/{employee_id}/{skill_id} — Current mastery detail (§8.7) ---
@router.get("/{employee_id}/{skill_id}", response_model=MasteryDecisionOut)
async def get_mastery_detail(
    employee_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent mastery decision for an employee+skill (§8.7)."""
    _validate_mastery_access(employee_id, current_user)

    result = await db.exec(
        select(MasteryHistory)
        .where(
            MasteryHistory.employee_id == employee_id,
            MasteryHistory.skill_id == skill_id,
        )
        .order_by(MasteryHistory.created_at.desc())
        .limit(1)
    )
    entry = result.first()

    if not entry:
        raise HTTPException(
            status_code=404,
            detail="No mastery decisions found for this employee+skill",
        )

    return MasteryDecisionOut.model_validate(entry)
