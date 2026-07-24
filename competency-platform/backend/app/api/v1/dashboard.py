# app/api/v1/dashboard.py
"""Manager Dashboard API — §8.6 Dashboard Routes.

From §21.4 Flow 4 (Manager Dashboard Data Load):
  1. GET /dashboard/overview — aggregate query; Redis cache 5 min TTL
  2. GET /dashboard/team-progress — join users + states + competencies; paginated
  3. GET /dashboard/pending-reviews — competencies with status = 'under_review'
  4. GET /dashboard/skill-gaps — skills where mastery below target; sorted by gap

From §20 RBAC Permission Matrix:
  - All endpoints require 'manager' or 'admin' role
  - Manager sees only their team (same tenant, department scope)
  - Admin sees all users within the tenant
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select, func, col, and_, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import desc
from redis.asyncio import Redis

from app.core.db import get_async_session
from app.core.redis import get_redis
from app.core.errors import PlatformError, ErrorCodes
from app.api.dependencies import require_role
from app.models.user import User
from app.models.competency import Competency, Skill
from app.models.learning_state import EmployeeLearningState
from app.models.assessment import MasteryHistory
from app.schemas.dashboard import (
    DashboardOverview,
    TeamProgressResponse,
    EmployeeSkillProgress,
    SkillGapsResponse,
    SkillGapItem,
    RecentMasteryResponse,
    RecentMasteryItem,
    PendingReviewsResponse,
    PendingReviewItem,
    MasteryOverrideRequest,
    MasteryOverrideResponse,
)

logger = structlog.get_logger()

router = APIRouter()

# Redis cache TTL for dashboard overview (§5.2)
OVERVIEW_CACHE_TTL = 300  # 5 minutes in seconds


# ---------------------------------------------------------------------------
# Helper: Resolve team scope per §20 RBAC rules
# ---------------------------------------------------------------------------

def _team_filter(user: User):
    """Return SQLAlchemy filter for team scoping.

    §20 RBAC Matrix:
      - Admin: sees all users in tenant
      - Manager: sees employees in same tenant AND same department
    """
    if user.role == "admin":
        # Admin sees all employees in their tenant
        return and_(
            User.tenant_id == user.tenant_id,
            User.role == "employee",
            User.is_active == True,  # noqa: E712
        )
    else:
        # Manager sees employees in same tenant + department
        return and_(
            User.tenant_id == user.tenant_id,
            User.department == user.department,
            User.role == "employee",
            User.is_active == True,  # noqa: E712
        )


async def _get_team_ids(
    session: AsyncSession, user: User
) -> list[uuid.UUID]:
    """Get list of employee UUIDs that this manager/admin can see."""
    stmt = select(User.id).where(_team_filter(user))
    result = await session.exec(stmt)
    return list(result.all())


# ---------------------------------------------------------------------------
# 1. GET /dashboard/overview — §8.6, §21.4 Step 1
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=DashboardOverview)
async def get_dashboard_overview(
    user: User = Depends(require_role("manager", "admin")),
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
):
    """Aggregated summary statistics for the manager dashboard.

    Redis-cached with 5 min TTL per §5.2.
    §21.4 Flow 4, Step 1: GET /dashboard/overview.
    """
    # Check Redis cache first
    cache_key = f"dashboard:overview:{user.tenant_id}:{user.department or 'all'}"
    cached = await redis.get(cache_key)
    if cached:
        logger.info("dashboard_overview_cache_hit", user_id=str(user.id))
        return DashboardOverview(**json.loads(cached))

    logger.info("dashboard_overview_cache_miss", user_id=str(user.id))

    # Get team member IDs
    team_ids = await _get_team_ids(session, user)

    if not team_ids:
        overview = DashboardOverview(
            total_employees=0,
            active_learners=0,
            avg_mastery_level=0.0,
            avg_mastery_score=0.0,
            total_competencies=0,
            skills_mastered_count=0,
            recent_upgrades_30d=0,
            pending_reviews_count=0,
            avg_engagement_score=0.0,
        )
        await redis.setex(cache_key, OVERVIEW_CACHE_TTL, overview.model_dump_json())
        return overview

    total_employees = len(team_ids)

    # Active learners: employees with at least one learning state entry
    active_stmt = (
        select(func.count(func.distinct(EmployeeLearningState.employee_id)))
        .where(EmployeeLearningState.employee_id.in_(team_ids))
    )
    active_result = await session.exec(active_stmt)
    active_learners = active_result.one() or 0

    # Average mastery level and score across all employee-skill pairs
    avg_stmt = (
        select(
            func.coalesce(func.avg(EmployeeLearningState.mastery_level), 0).label("avg_level"),
            func.coalesce(func.avg(EmployeeLearningState.current_score), 0).label("avg_score"),
            func.coalesce(func.avg(EmployeeLearningState.engagement_score), 0).label("avg_engage"),
        )
        .where(EmployeeLearningState.employee_id.in_(team_ids))
    )
    avg_result = await session.exec(avg_stmt)
    avg_row = avg_result.one()

    # Skills mastered: mastery_level >= 4 (ADVANCED or MASTERED)
    mastered_stmt = (
        select(func.count())
        .where(
            EmployeeLearningState.employee_id.in_(team_ids),
            EmployeeLearningState.mastery_level >= 4,
        )
    )
    mastered_result = await session.exec(mastered_stmt)
    skills_mastered = mastered_result.one() or 0

    # Recent upgrades in last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    upgrades_stmt = (
        select(func.count())
        .select_from(MasteryHistory)
        .where(
            MasteryHistory.employee_id.in_(team_ids),
            MasteryHistory.decision == "UPGRADE",
            MasteryHistory.created_at >= thirty_days_ago,
        )
    )
    upgrades_result = await session.exec(upgrades_stmt)
    recent_upgrades = upgrades_result.one() or 0

    # Pending reviews: competencies with status = 'under_review' in tenant
    pending_stmt = (
        select(func.count())
        .select_from(Competency)
        .where(
            Competency.tenant_id == user.tenant_id,
            Competency.status == "under_review",
        )
    )
    pending_result = await session.exec(pending_stmt)
    pending_reviews = pending_result.one() or 0

    # Total competencies in tenant
    comp_stmt = (
        select(func.count())
        .select_from(Competency)
        .where(Competency.tenant_id == user.tenant_id)
    )
    comp_result = await session.exec(comp_stmt)
    total_competencies = comp_result.one() or 0

    overview = DashboardOverview(
        total_employees=total_employees,
        active_learners=active_learners,
        avg_mastery_level=round(float(avg_row.avg_level), 2),
        avg_mastery_score=round(float(avg_row.avg_score), 2),
        total_competencies=total_competencies,
        skills_mastered_count=skills_mastered,
        recent_upgrades_30d=recent_upgrades,
        pending_reviews_count=pending_reviews,
        avg_engagement_score=round(float(avg_row.avg_engage), 2),
    )

    # Cache in Redis with 5 min TTL (§5.2)
    await redis.setex(cache_key, OVERVIEW_CACHE_TTL, overview.model_dump_json())
    logger.info(
        "dashboard_overview_cached",
        user_id=str(user.id),
        ttl=OVERVIEW_CACHE_TTL,
        active_learners=active_learners,
    )

    return overview


# ---------------------------------------------------------------------------
# 2. GET /dashboard/team-progress — §8.6, §21.4 Step 2
# ---------------------------------------------------------------------------

@router.get("/team-progress", response_model=TeamProgressResponse)
async def get_team_progress(
    user: User = Depends(require_role("manager", "admin")),
    session: AsyncSession = Depends(get_async_session),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    competency_id: Optional[uuid.UUID] = Query(None, description="Filter by competency"),
    employee_id: Optional[uuid.UUID] = Query(None, description="Filter by employee"),
):
    """Team competency progress matrix — all employees × all skills.

    §21.4 Flow 4, Step 2: join users + states + competencies; paginated.
    Returns each employee-skill combination with current mastery state.
    """
    team_ids = await _get_team_ids(session, user)

    if not team_ids:
        return TeamProgressResponse(items=[], total=0, skip=skip, limit=limit, has_more=False)

    # If filtering by employee, verify they are in the team
    if employee_id and employee_id not in team_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee not in your team scope",
        )

    # Build the join: EmployeeLearningState + User + Skill + Competency
    base_filter = [EmployeeLearningState.employee_id.in_(team_ids)]

    if competency_id:
        base_filter.append(EmployeeLearningState.competency_id == competency_id)
    if employee_id:
        base_filter.append(EmployeeLearningState.employee_id == employee_id)

    # Count total
    count_stmt = (
        select(func.count())
        .select_from(EmployeeLearningState)
        .where(*base_filter)
    )
    count_result = await session.exec(count_stmt)
    total = count_result.one() or 0

    # Fetch paginated data with joins
    data_stmt = (
        select(
            EmployeeLearningState,
            User.full_name.label("employee_name"),
            User.email.label("employee_email"),
            Skill.name.label("skill_name"),
            Skill.mastery_threshold.label("target_mastery"),
            Competency.name.label("competency_name"),
        )
        .join(User, EmployeeLearningState.employee_id == User.id)
        .join(Skill, EmployeeLearningState.skill_id == Skill.id)
        .join(Competency, EmployeeLearningState.competency_id == Competency.id)
        .where(*base_filter)
        .order_by(User.full_name, Skill.name)
        .offset(skip)
        .limit(limit)
    )
    data_result = await session.exec(data_stmt)
    rows = data_result.all()

    items = [
        EmployeeSkillProgress(
            employee_id=row.EmployeeLearningState.employee_id,
            employee_name=row.employee_name,
            employee_email=row.employee_email,
            skill_id=row.EmployeeLearningState.skill_id,
            skill_name=row.skill_name,
            competency_id=row.EmployeeLearningState.competency_id,
            competency_name=row.competency_name,
            current_score=row.EmployeeLearningState.current_score,
            mastery_level=row.EmployeeLearningState.mastery_level,
            mastery_confidence=row.EmployeeLearningState.mastery_confidence,
            target_mastery=row.target_mastery,
            sessions_count=row.EmployeeLearningState.sessions_count,
            last_assessed_at=row.EmployeeLearningState.last_assessed_at,
        )
        for row in rows
    ]

    return TeamProgressResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )


# ---------------------------------------------------------------------------
# 3. GET /dashboard/skill-gaps — §8.6, §21.4 Step 4
# ---------------------------------------------------------------------------

@router.get("/skill-gaps", response_model=SkillGapsResponse)
async def get_skill_gaps(
    user: User = Depends(require_role("manager", "admin")),
    session: AsyncSession = Depends(get_async_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    min_gap: float = Query(0.0, ge=0.0, le=1.0, description="Minimum gap severity to include"),
):
    """Skills below target mastery level across team, sorted by gap severity.

    §21.4 Flow 4, Step 4: skills where mastery_level below target; sorted by gap.

    Gap severity formula:
      gap_severity = skill.mastery_threshold - (state.mastery_level / 5.0)

    Higher gap_severity = more urgent training need.
    Only includes rows where gap_severity > 0 (i.e., below target).
    """
    team_ids = await _get_team_ids(session, user)

    if not team_ids:
        return SkillGapsResponse(items=[], total=0, skip=skip, limit=limit)

    # Compute gap severity as a SQL expression
    gap_expr = (
        Skill.mastery_threshold - (EmployeeLearningState.mastery_level / 5.0)
    ).label("gap_severity")

    base_conditions = [
        EmployeeLearningState.employee_id.in_(team_ids),
        # Only include where there IS a gap (current below target)
        (Skill.mastery_threshold - (EmployeeLearningState.mastery_level / 5.0)) > min_gap,
    ]

    # Count total gaps
    count_stmt = (
        select(func.count())
        .select_from(EmployeeLearningState)
        .join(Skill, EmployeeLearningState.skill_id == Skill.id)
        .where(*base_conditions)
    )
    count_result = await session.exec(count_stmt)
    total = count_result.one() or 0

    # Fetch gaps sorted by severity descending
    data_stmt = (
        select(
            EmployeeLearningState,
            User.full_name.label("employee_name"),
            Skill.name.label("skill_name"),
            Skill.mastery_threshold.label("target_mastery"),
            Competency.name.label("competency_name"),
            gap_expr,
        )
        .join(User, EmployeeLearningState.employee_id == User.id)
        .join(Skill, EmployeeLearningState.skill_id == Skill.id)
        .join(Competency, EmployeeLearningState.competency_id == Competency.id)
        .where(*base_conditions)
        .order_by(desc("gap_severity"))
        .offset(skip)
        .limit(limit)
    )
    data_result = await session.exec(data_stmt)
    rows = data_result.all()

    items = [
        SkillGapItem(
            employee_id=row.EmployeeLearningState.employee_id,
            employee_name=row.employee_name,
            skill_id=row.EmployeeLearningState.skill_id,
            skill_name=row.skill_name,
            competency_name=row.competency_name,
            current_mastery_level=row.EmployeeLearningState.mastery_level,
            target_mastery=row.target_mastery,
            gap_severity=round(float(row.gap_severity), 4),
            current_score=row.EmployeeLearningState.current_score,
            sessions_count=row.EmployeeLearningState.sessions_count,
            last_assessed_at=row.EmployeeLearningState.last_assessed_at,
        )
        for row in rows
    ]

    return SkillGapsResponse(items=items, total=total, skip=skip, limit=limit)


# ---------------------------------------------------------------------------
# 4. GET /dashboard/recent-mastery — §8.6
# ---------------------------------------------------------------------------

@router.get("/recent-mastery", response_model=RecentMasteryResponse)
async def get_recent_mastery(
    user: User = Depends(require_role("manager", "admin")),
    session: AsyncSession = Depends(get_async_session),
    days: int = Query(30, ge=1, le=90, description="Look-back window in days"),
):
    """Recently achieved mastery upgrades across the team.

    Returns MasteryHistory entries with decision = 'UPGRADE'
    from the last N days (default 30), ordered newest first.
    """
    team_ids = await _get_team_ids(session, user)

    if not team_ids:
        return RecentMasteryResponse(items=[], total=0)

    cutoff = datetime.utcnow() - timedelta(days=days)

    stmt = (
        select(
            MasteryHistory,
            User.full_name.label("employee_name"),
            Skill.name.label("skill_name"),
        )
        .join(User, MasteryHistory.employee_id == User.id)
        .join(Skill, MasteryHistory.skill_id == Skill.id)
        .where(
            MasteryHistory.employee_id.in_(team_ids),
            MasteryHistory.decision == "UPGRADE",
            MasteryHistory.created_at >= cutoff,
        )
        .order_by(desc(MasteryHistory.created_at))
    )
    result = await session.exec(stmt)
    rows = result.all()

    items = [
        RecentMasteryItem(
            employee_id=row.MasteryHistory.employee_id,
            employee_name=row.employee_name,
            skill_id=row.MasteryHistory.skill_id,
            skill_name=row.skill_name,
            old_level=row.MasteryHistory.old_level,
            new_level=row.MasteryHistory.new_level,
            decision=row.MasteryHistory.decision,
            confidence=row.MasteryHistory.confidence,
            evidence_summary=row.MasteryHistory.evidence_summary,
            decided_by=row.MasteryHistory.decided_by,
            created_at=row.MasteryHistory.created_at,
        )
        for row in rows
    ]

    return RecentMasteryResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# 5. GET /dashboard/pending-reviews — §8.6, §21.4 Step 3
# ---------------------------------------------------------------------------

@router.get("/pending-reviews", response_model=PendingReviewsResponse)
async def get_pending_reviews(
    user: User = Depends(require_role("manager", "admin")),
    session: AsyncSession = Depends(get_async_session),
):
    """Competencies awaiting manager validation (status = 'under_review').

    §21.4 Flow 4, Step 3: competencies with status = 'under_review'.
    Includes skill count and decomposition confidence for each competency.
    """
    # Subquery: count skills per competency
    skill_count_sq = (
        select(
            Skill.competency_id,
            func.count(Skill.id).label("skill_count"),
        )
        .group_by(Skill.competency_id)
        .subquery()
    )

    stmt = (
        select(
            Competency,
            User.full_name.label("creator_name"),
            func.coalesce(skill_count_sq.c.skill_count, 0).label("skill_count"),
        )
        .join(User, Competency.created_by == User.id)
        .outerjoin(skill_count_sq, Competency.id == skill_count_sq.c.competency_id)
        .where(
            Competency.tenant_id == user.tenant_id,
            Competency.status == "under_review",
        )
        .order_by(Competency.created_at)
    )
    result = await session.exec(stmt)
    rows = result.all()

    items = [
        PendingReviewItem(
            competency_id=row.Competency.id,
            competency_name=row.Competency.name,
            description=row.Competency.description,
            status=row.Competency.status,
            created_by=row.Competency.created_by,
            creator_name=row.creator_name,
            skill_count=row.skill_count,
            decomp_confidence=row.Competency.decomp_confidence,
            created_at=row.Competency.created_at,
            updated_at=row.Competency.updated_at,
        )
        for row in rows
    ]

    return PendingReviewsResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# 6. POST /dashboard/mastery-override — §8.6, §20 RBAC
# ---------------------------------------------------------------------------

@router.post(
    "/mastery-override",
    response_model=MasteryOverrideResponse,
    status_code=status.HTTP_201_CREATED,
)
async def mastery_override(
    body: MasteryOverrideRequest,
    user: User = Depends(require_role("manager", "admin")),
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
):
    """Manager overrides a mastery decision for an employee's skill.

    §8.6 POST /dashboard/mastery-override:
    Creates an append-only MasteryHistory record with:
      - decided_by = 'manager_override'
      - override_reason = manager's justification text

    Also updates the EmployeeLearningState.mastery_level in-place.
    Invalidates Redis cache for both the employee's mastery key and
    the dashboard overview cache.
    """
    # Verify the employee is in manager's team scope
    team_ids = await _get_team_ids(session, user)

    if body.employee_id not in team_ids:
        raise PlatformError(
            code=ErrorCodes.PERMISSION_DENIED,
            message="Employee is not in your team scope",
            detail=f"Employee {body.employee_id} is not accessible to your role",
            status_code=403,
        )

    # Fetch current learning state
    state_stmt = select(EmployeeLearningState).where(
        EmployeeLearningState.employee_id == body.employee_id,
        EmployeeLearningState.skill_id == body.skill_id,
    )
    state_result = await session.exec(state_stmt)
    learning_state = state_result.first()

    if not learning_state:
        raise PlatformError(
            code="SKILL_NOT_FOUND",
            message="No learning state found for this employee-skill pair",
            detail=f"employee={body.employee_id}, skill={body.skill_id}",
            status_code=404,
        )

    old_level = learning_state.mastery_level

    # Determine decision based on level change
    if body.new_mastery_level > old_level:
        decision = "UPGRADE"
    elif body.new_mastery_level < old_level:
        decision = "DOWNGRADE"
    else:
        decision = "MAINTAIN"

    # Create append-only MasteryHistory record (§6.1 mastery_history table)
    history_record = MasteryHistory(
        employee_id=body.employee_id,
        skill_id=body.skill_id,
        old_level=old_level,
        new_level=body.new_mastery_level,
        decision=decision,
        confidence=1.0,  # Manager override = full confidence
        evidence_summary=f"Manager override by {user.full_name}: {body.override_reason}",
        decided_by="manager_override",
        override_reason=body.override_reason,
        session_id=None,  # No session for manual overrides
    )
    session.add(history_record)

    # Update the live learning state
    learning_state.mastery_level = body.new_mastery_level
    learning_state.updated_at = datetime.utcnow()
    session.add(learning_state)

    await session.commit()
    await session.refresh(history_record)

    # Invalidate Redis caches (§5.2 mastery:{emp_id}:{skill_id})
    mastery_cache_key = f"mastery:{body.employee_id}:{body.skill_id}"
    overview_cache_key = f"dashboard:overview:{user.tenant_id}:{user.department or 'all'}"
    await redis.delete(mastery_cache_key, overview_cache_key)

    logger.info(
        "mastery_override_applied",
        manager_id=str(user.id),
        employee_id=str(body.employee_id),
        skill_id=str(body.skill_id),
        old_level=old_level,
        new_level=body.new_mastery_level,
        decision=decision,
    )

    return MasteryOverrideResponse(
        history_id=history_record.id,
        employee_id=body.employee_id,
        skill_id=body.skill_id,
        old_level=old_level,
        new_level=body.new_mastery_level,
        decision=decision,
        decided_by="manager_override",
        override_reason=body.override_reason,
        overridden_by=user.id,
        created_at=history_record.created_at or datetime.utcnow(),
    )
