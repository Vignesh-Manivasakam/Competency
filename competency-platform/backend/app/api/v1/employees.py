# app/api/v1/employees.py
"""Employee management, assignment, and learning state endpoints.

§8.4 Employee and Learning State Routes
§21.2 Flow 2: Employee Baseline Assessment
§9.3 RBAC: require_role('manager', 'admin') for management routes
"""
import uuid
import math
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select, func, col
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

from app.api.dependencies import get_current_user, require_role, get_async_session, get_redis
from app.core.errors import PlatformError
from app.core.security import get_password_hash
from app.models.user import User
from app.models.competency import Competency, Skill
from app.models.learning_state import EmployeeLearningState
from app.models.session import LearningSession
from app.models.assessment import AssessmentResult, MasteryHistory
from app.agents.learning_state_manager import LearningStateManagerAgent
from app.schemas.session import (
    EmployeeCreateRequest,
    EmployeeOut,
    EmployeeAssignRequest,
    BaselineAssessmentRequest,
    BaselineAssessmentResponse,
    LearningStateOut,
    CompetencyMatrixOut,
    SessionOut,
    AssessmentOut,
    PaginatedResponse,
)

logger = structlog.get_logger()

router = APIRouter()


def _validate_employee_access(employee_id: uuid.UUID, current_user: User):
    """Employees can only access their own data; managers/admins can access
    any employee in their tenant (§9.3).
    """
    if current_user.role == "employee" and current_user.id != employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


# --- GET /employees — List employees (manager scope) ---
@router.get("", response_model=PaginatedResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    department: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("manager", "admin")),
):
    """List employees scoped to the manager's tenant (§8.4, §9.3).
    Managers can only see employees within their own tenant.
    """
    query = select(User).where(
        User.tenant_id == current_user.tenant_id,
        User.role == "employee",
    )
    count_query = select(func.count(User.id)).where(
        User.tenant_id == current_user.tenant_id,
        User.role == "employee",
    )

    if department:
        query = query.where(User.department == department)
        count_query = count_query.where(User.department == department)

    if search:
        query = query.where(
            col(User.full_name).ilike(f"%{search}%")
            | col(User.email).ilike(f"%{search}%")
        )
        count_query = count_query.where(
            col(User.full_name).ilike(f"%{search}%")
            | col(User.email).ilike(f"%{search}%")
        )

    total = (await db.exec(count_query)).one()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(User.full_name)
    result = await db.exec(query)
    employees = result.all()

    return PaginatedResponse(
        items=[EmployeeOut.model_validate(e) for e in employees],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# --- POST /employees — Create employee account ---
@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreateRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("manager", "admin")),
):
    """Create a new employee account in the manager's tenant (§8.4).
    Only managers and admins can create employee accounts.
    """
    # Check for duplicate email
    existing = await db.exec(select(User).where(User.email == body.email))
    if existing.first():
        raise PlatformError(
            code="DUPLICATE_EMAIL",
            message="An account with this email already exists",
            status_code=409,
        )

    employee = User(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        full_name=body.full_name,
        role="employee",
        job_title=body.job_title,
        department=body.department,
        tenant_id=current_user.tenant_id,
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    logger.info("employee_created", employee_id=str(employee.id), by=str(current_user.id))
    return EmployeeOut.model_validate(employee)


# --- GET /employees/{id} — Get employee profile ---
@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get employee profile (§8.4).
    Employees can view their own profile; managers/admins can view any
    employee in their tenant.
    """
    employee = await db.get(User, employee_id)
    if not employee or employee.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    _validate_employee_access(employee_id, current_user)

    return EmployeeOut.model_validate(employee)


# --- POST /employees/{id}/assign — Assign employee to competency (§21.2 Step 1) ---
@router.post("/{employee_id}/assign", status_code=status.HTTP_200_OK)
async def assign_employee_to_competency(
    employee_id: uuid.UUID,
    body: EmployeeAssignRequest,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(require_role("manager", "admin")),
):
    """Assign employee to a competency version (§21.2 Step 1).
    Creates EmployeeLearningState rows for all skills in the competency.
    Competency must be in 'active' status (validated).
    """
    # Validate employee exists in tenant
    employee = await db.get(User, employee_id)
    if not employee or employee.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Validate competency is active (§19.2 COMPETENCY_NOT_VALIDATED)
    competency = await db.get(Competency, body.competency_id)
    if not competency or competency.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Competency not found")

    if competency.status != "active":
        raise PlatformError(
            code="COMPETENCY_NOT_VALIDATED",
            message="Competency must be in 'active' status before assignment",
            detail=f"Current status: {competency.status}",
            status_code=409,
        )

    # Fetch all skills for this competency
    result = await db.exec(
        select(Skill).where(Skill.competency_id == competency.id)
    )
    skills = result.all()

    if not skills:
        raise PlatformError(
            code="COMPETENCY_NOT_VALIDATED",
            message="Competency has no skills defined",
            status_code=409,
        )

    # Initialize learning state for each skill (skip if already exists)
    state_mgr = LearningStateManagerAgent(db, redis)
    created_count = 0

    for skill in skills:
        existing = await db.exec(
            select(EmployeeLearningState).where(
                EmployeeLearningState.employee_id == employee_id,
                EmployeeLearningState.skill_id == skill.id,
            )
        )
        if not existing.first():
            await state_mgr.initialize_learning_state(
                employee_id=str(employee_id),
                skill_id=str(skill.id),
                competency_id=str(competency.id),
            )
            created_count += 1

    logger.info(
        "employee_assigned",
        employee_id=str(employee_id),
        competency_id=str(competency.id),
        skills_initialized=created_count,
    )

    return {
        "message": f"Employee assigned to competency '{competency.name}'",
        "competency_id": str(competency.id),
        "skills_count": len(skills),
        "new_states_created": created_count,
    }


# --- POST /employees/{id}/baseline — Trigger baseline assessment (§21.2 Step 2) ---
@router.post("/{employee_id}/baseline", response_model=BaselineAssessmentResponse)
async def trigger_baseline_assessment(
    employee_id: uuid.UUID,
    body: BaselineAssessmentRequest,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(require_role("manager", "admin")),
):
    """Trigger baseline assessment session for an employee (§21.2 Step 2).

    Creates a baseline LearningSession. The frontend then connects via
    WebSocket at /api/v1/sessions/{session_id}/ws where the
    baseline_assessment_graph runs 8-12 adaptive questions.
    On completion, the Learning State Manager initialises learning
    state rows for all skills with initial mastery levels.
    """
    # Validate employee
    employee = await db.get(User, employee_id)
    if not employee or employee.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Validate competency
    competency = await db.get(Competency, body.competency_id)
    if not competency or competency.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Competency not found")

    if competency.status != "active":
        raise PlatformError(
            code="COMPETENCY_NOT_VALIDATED",
            message="Competency must be active for baseline assessment",
            status_code=409,
        )

    # Check for already active baseline session (§19.2 SESSION_ALREADY_ACTIVE)
    active_result = await db.exec(
        select(LearningSession).where(
            LearningSession.employee_id == employee_id,
            LearningSession.competency_id == competency.id,
            LearningSession.session_type == "baseline",
            LearningSession.status == "active",
        )
    )
    if active_result.first():
        raise PlatformError(
            code="SESSION_ALREADY_ACTIVE",
            message="A baseline assessment session is already active for this employee",
            status_code=409,
        )

    # Pick first skill as entry point for baseline (covers whole competency)
    skills_result = await db.exec(
        select(Skill)
        .where(Skill.competency_id == competency.id)
        .order_by(Skill.hierarchy_level, Skill.difficulty_level)
    )
    first_skill = skills_result.first()
    if not first_skill:
        raise PlatformError(
            code="COMPETENCY_NOT_VALIDATED",
            message="No skills found in competency",
            status_code=409,
        )

    # Create baseline session in PostgreSQL
    session = LearningSession(
        employee_id=employee_id,
        skill_id=first_skill.id,
        competency_id=competency.id,
        status="active",
        session_type="baseline",
        started_at=datetime.utcnow(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Initialize session state in Redis
    state_mgr = LearningStateManagerAgent(db, redis)
    await state_mgr.create_session_state(str(session.id), {
        "session_id": str(session.id),
        "employee_id": str(employee_id),
        "competency_id": str(competency.id),
        "session_type": "baseline",
        "interaction_count": 0,
        "scores": [],
        "messages": [],
        "status": "active",
    })

    logger.info(
        "baseline_session_created",
        session_id=str(session.id),
        employee_id=str(employee_id),
        competency_id=str(competency.id),
    )

    return BaselineAssessmentResponse(
        session_id=session.id,
        ws_url=f"/api/v1/sessions/{session.id}/ws",
    )


# --- GET /employees/{id}/learning-state — All learning states (§8.4) ---
@router.get("/{employee_id}/learning-state", response_model=list[LearningStateOut])
async def get_all_learning_states(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get all learning states for an employee across all skills (§8.4)."""
    _validate_employee_access(employee_id, current_user)

    result = await db.exec(
        select(EmployeeLearningState)
        .where(EmployeeLearningState.employee_id == employee_id)
        .order_by(EmployeeLearningState.competency_id, EmployeeLearningState.skill_id)
    )
    states = result.all()
    return [LearningStateOut.model_validate(s) for s in states]


# --- GET /employees/{id}/learning-state/{skill_id} — Single skill state (§8.4) ---
@router.get("/{employee_id}/learning-state/{skill_id}", response_model=LearningStateOut)
async def get_skill_learning_state(
    employee_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get learning state for a specific employee + skill (§8.4)."""
    _validate_employee_access(employee_id, current_user)

    result = await db.exec(
        select(EmployeeLearningState).where(
            EmployeeLearningState.employee_id == employee_id,
            EmployeeLearningState.skill_id == skill_id,
        )
    )
    state = result.first()
    if not state:
        raise HTTPException(status_code=404, detail="Learning state not found")

    return LearningStateOut.model_validate(state)


# --- GET /employees/{id}/competency-matrix — Full competency matrix (§8.4) ---
@router.get("/{employee_id}/competency-matrix", response_model=list[CompetencyMatrixOut])
async def get_competency_matrix(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Get full competency matrix for employee (§8.4).
    Delegates to LearningStateManagerAgent which caches in Redis (5-min TTL).
    """
    _validate_employee_access(employee_id, current_user)

    state_mgr = LearningStateManagerAgent(db, redis)
    matrix = await state_mgr.get_competency_matrix(str(employee_id))
    return [CompetencyMatrixOut(**entry) for entry in matrix]


# --- GET /employees/{id}/history — Assessment history (paginated) (§8.4) ---
@router.get("/{employee_id}/history", response_model=PaginatedResponse)
async def get_assessment_history(
    employee_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    skill_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get paginated assessment history for an employee (§8.4)."""
    _validate_employee_access(employee_id, current_user)

    query = select(AssessmentResult).where(
        AssessmentResult.employee_id == employee_id
    )
    count_query = select(func.count(AssessmentResult.id)).where(
        AssessmentResult.employee_id == employee_id
    )

    if skill_id:
        query = query.where(AssessmentResult.skill_id == skill_id)
        count_query = count_query.where(AssessmentResult.skill_id == skill_id)

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


# --- GET /employees/{id}/sessions — Learning sessions list (§8.4) ---
@router.get("/{employee_id}/sessions", response_model=PaginatedResponse)
async def list_employee_sessions(
    employee_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    session_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """List learning sessions for an employee with pagination (§8.4)."""
    _validate_employee_access(employee_id, current_user)

    query = select(LearningSession).where(
        LearningSession.employee_id == employee_id
    )
    count_query = select(func.count(LearningSession.id)).where(
        LearningSession.employee_id == employee_id
    )

    if status_filter:
        query = query.where(LearningSession.status == status_filter)
        count_query = count_query.where(LearningSession.status == status_filter)

    if session_type:
        query = query.where(LearningSession.session_type == session_type)
        count_query = count_query.where(LearningSession.session_type == session_type)

    total = (await db.exec(count_query)).one()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    offset = (page - 1) * page_size
    query = query.order_by(LearningSession.started_at.desc()).offset(offset).limit(page_size)
    result = await db.exec(query)
    sessions = result.all()

    return PaginatedResponse(
        items=[SessionOut.model_validate(s) for s in sessions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
