# app/api/v1/assessments.py
"""Assessment result query endpoints.

§8.7 Mastery and Assessment Routes
GET /assessments/{id} — Get single assessment result
GET /assessments — List assessments (filtered by employee/skill/session)
"""
import uuid
import math
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies import get_current_user, get_async_session
from app.models.user import User
from app.models.assessment import AssessmentResult
from app.schemas.session import AssessmentOut, PaginatedResponse

logger = structlog.get_logger()

router = APIRouter()


# --- GET /assessments — List assessments (filtered) (§8.7) ---
@router.get("", response_model=PaginatedResponse)
async def list_assessments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    employee_id: Optional[uuid.UUID] = None,
    skill_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    assessment_mode: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """List assessments with optional filters (§8.7).
    Employees can only query their own assessments.
    """
    query = select(AssessmentResult)
    count_query = select(func.count(AssessmentResult.id))

    # Employees are scoped to their own assessments
    if current_user.role == "employee":
        query = query.where(AssessmentResult.employee_id == current_user.id)
        count_query = count_query.where(AssessmentResult.employee_id == current_user.id)
    elif employee_id:
        query = query.where(AssessmentResult.employee_id == employee_id)
        count_query = count_query.where(AssessmentResult.employee_id == employee_id)

    if skill_id:
        query = query.where(AssessmentResult.skill_id == skill_id)
        count_query = count_query.where(AssessmentResult.skill_id == skill_id)

    if session_id:
        query = query.where(AssessmentResult.session_id == session_id)
        count_query = count_query.where(AssessmentResult.session_id == session_id)

    if assessment_mode:
        query = query.where(AssessmentResult.assessment_mode == assessment_mode)
        count_query = count_query.where(AssessmentResult.assessment_mode == assessment_mode)

    total = (await db.exec(count_query)).one()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    offset = (page - 1) * page_size
    query = query.order_by(AssessmentResult.created_at.desc()).offset(offset).limit(page_size)
    result = await db.exec(query)
    assessments = result.all()

    return PaginatedResponse(
        items=[AssessmentOut.model_validate(a) for a in assessments],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# --- GET /assessments/{id} — Get single assessment (§8.7) ---
@router.get("/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get a single assessment result by ID (§8.7)."""
    assessment = await db.get(AssessmentResult, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Employees can only view their own assessments
    if current_user.role == "employee" and assessment.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return AssessmentOut.model_validate(assessment)
