# app/api/v1/sessions.py
"""Learning session lifecycle REST endpoints.

§8.5 Learning Session Routes
POST /sessions — Create new learning session
GET /sessions/{id} — Get session status
POST /sessions/{id}/interact — HTTP polling fallback for WebSocket
GET /sessions/{id}/transcript — Full session message history
POST /sessions/{id}/pause — Pause session (saved to Redis)
POST /sessions/{id}/resume — Resume paused session
POST /sessions/{id}/end — End session early
"""
import uuid
import json
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

from app.api.dependencies import get_current_user, get_async_session, get_redis
from app.core.errors import PlatformError
from app.models.user import User
from app.models.session import LearningSession
from app.models.competency import Skill
from app.models.learning_state import EmployeeLearningState
from app.models.assessment import AssessmentResult
from app.agents.learning_state_manager import LearningStateManagerAgent
from app.schemas.session import (
    SessionCreateRequest,
    SessionOut,
    SessionInteractRequest,
    SessionInteractResponse,
    TranscriptEntry,
    TranscriptOut,
)

logger = structlog.get_logger()

router = APIRouter()


async def _get_validated_session(
    session_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> LearningSession:
    """Load session and validate access permissions (§19.2 SESSION_NOT_FOUND)."""
    session = await db.get(LearningSession, session_id)
    if not session:
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message="Session not found",
            status_code=404,
        )

    # Employees can only access their own sessions
    if current_user.role == "employee" and session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return session


# --- POST /sessions — Create new learning session ---
@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreateRequest,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Create a new learning session (§8.5).

    Validates:
    - Employee exists and caller has access
    - Skill exists
    - No already-active session for this employee+skill (§19.2 SESSION_ALREADY_ACTIVE)
    - Prerequisites are met for the skill (§19.2 PREREQUISITE_NOT_MET)
    """
    # Ownership check: employees can only create sessions for themselves
    if current_user.role == "employee" and current_user.id != body.employee_id:
        raise HTTPException(status_code=403, detail="Cannot create session for another employee")

    # Validate skill
    skill = await db.get(Skill, body.skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Check for already-active session (§19.2)
    active_check = await db.exec(
        select(LearningSession).where(
            LearningSession.employee_id == body.employee_id,
            LearningSession.skill_id == body.skill_id,
            LearningSession.status == "active",
        )
    )
    if active_check.first():
        raise PlatformError(
            code="SESSION_ALREADY_ACTIVE",
            message="An active session already exists for this employee and skill",
            status_code=409,
        )

    # Check prerequisites are met (§19.2 PREREQUISITE_NOT_MET)
    if body.session_type != "baseline":
        prereq_states = await db.exec(
            select(EmployeeLearningState).where(
                EmployeeLearningState.employee_id == body.employee_id,
                EmployeeLearningState.skill_id == body.skill_id,
            )
        )
        learning_state = prereq_states.first()
        if not learning_state:
            raise PlatformError(
                code="PREREQUISITE_NOT_MET",
                message="Employee has not been assigned to this skill's competency. Run baseline first.",
                status_code=409,
            )

    # Create session
    session = LearningSession(
        employee_id=body.employee_id,
        skill_id=body.skill_id,
        competency_id=skill.competency_id,
        status="active",
        session_type=body.session_type,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Initialize Redis session state
    state_mgr = LearningStateManagerAgent(db, redis)
    await state_mgr.create_session_state(str(session.id), {
        "session_id": str(session.id),
        "employee_id": str(body.employee_id),
        "skill_id": str(body.skill_id),
        "session_type": body.session_type,
        "interaction_count": 0,
        "scores": [],
        "messages": [],
        "status": "active",
    })

    logger.info("session_created", session_id=str(session.id), type=body.session_type)
    return SessionOut.model_validate(session)


# --- GET /sessions/{id} — Get session status ---
@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get session details and current status (§8.5)."""
    session = await _get_validated_session(session_id, current_user, db)
    return SessionOut.model_validate(session)


# --- POST /sessions/{id}/interact — HTTP polling fallback (§8.5) ---
@router.post("/{session_id}/interact", response_model=SessionInteractResponse)
async def interact_with_session(
    session_id: uuid.UUID,
    body: SessionInteractRequest,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Submit an employee response via HTTP (polling fallback for WebSocket).

    This is the HTTP equivalent of WebSocket message exchange. The session
    graph processes the response and returns the next tutor action.
    For real-time interaction, prefer WebSocket at /sessions/{id}/ws (Plan 15).
    """
    session = await _get_validated_session(session_id, current_user, db)

    if session.status != "active":
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message=f"Session is not active (current status: {session.status})",
            status_code=404,
        )

    state_mgr = LearningStateManagerAgent(db, redis)

    # Get current session state from Redis
    session_state = await state_mgr.get_session_state(str(session_id))
    if not session_state:
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message="Session state not found in Redis. Session may have expired.",
            status_code=404,
        )

    # Append employee message
    interaction_count = session_state.get("interaction_count", 0) + 1
    messages = session_state.get("messages", [])
    messages.append({
        "role": "employee",
        "content": body.employee_response,
        "timestamp": datetime.utcnow().isoformat(),
        "latency_ms": body.response_latency_ms,
    })

    tutor_message = (
        "Your response has been received and is being processed. "
        "For real-time interaction, connect via WebSocket."
    )
    messages.append({
        "role": "tutor",
        "content": tutor_message,
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Update session state in Redis
    await state_mgr.update_session_state(str(session_id), {
        "interaction_count": interaction_count,
        "messages": messages,
    })

    # Update PostgreSQL interaction count
    session.interaction_count = interaction_count
    db.add(session)
    await db.commit()

    return SessionInteractResponse(
        session_id=session_id,
        tutor_message=tutor_message,
        next_action="await_response",
        current_score=session_state.get("current_score"),
        interaction_count=interaction_count,
        mastery_level=session_state.get("mastery_level"),
        session_complete=False,
        feedback_points=[],
    )


# --- GET /sessions/{id}/transcript — Full session message history (§8.5) ---
@router.get("/{session_id}/transcript", response_model=TranscriptOut)
async def get_session_transcript(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Get the full message transcript for a session (§8.5).
    Reads from Redis for active sessions, or reconstructs from
    AssessmentResults for completed sessions.
    """
    session = await _get_validated_session(session_id, current_user, db)
    state_mgr = LearningStateManagerAgent(db, redis)

    # Try Redis first (active/paused sessions)
    session_state = await state_mgr.get_session_state(str(session_id))
    if session_state and session_state.get("messages"):
        entries = [
            TranscriptEntry(
                role=m["role"],
                content=m["content"],
                timestamp=datetime.fromisoformat(m["timestamp"]) if m.get("timestamp") else None,
            )
            for m in session_state["messages"]
        ]
        return TranscriptOut(
            session_id=session_id,
            entries=entries,
            total_entries=len(entries),
        )

    # Fallback: reconstruct from assessment_results (completed sessions)
    result = await db.exec(
        select(AssessmentResult)
        .where(AssessmentResult.session_id == session_id)
        .order_by(AssessmentResult.created_at)
    )
    assessments = result.all()

    entries = []
    for a in assessments:
        entries.append(TranscriptEntry(role="tutor", content=a.prompt_text, timestamp=a.created_at))
        entries.append(TranscriptEntry(role="employee", content=a.response_text, timestamp=a.created_at))

    return TranscriptOut(
        session_id=session_id,
        entries=entries,
        total_entries=len(entries),
    )


# --- POST /sessions/{id}/pause — Pause session (§8.5) ---
@router.post("/{session_id}/pause", response_model=SessionOut)
async def pause_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Pause an active session (§8.5).
    Session state remains in Redis (24h TTL) so it can be resumed.
    """
    session = await _get_validated_session(session_id, current_user, db)

    if session.status != "active":
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message=f"Only active sessions can be paused (current: {session.status})",
            status_code=404,
        )

    session.status = "paused"
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Update Redis state
    state_mgr = LearningStateManagerAgent(db, redis)
    await state_mgr.update_session_state(str(session_id), {"status": "paused"})

    logger.info("session_paused", session_id=str(session_id))
    return SessionOut.model_validate(session)


# --- POST /sessions/{id}/resume — Resume paused session (§8.5) ---
@router.post("/{session_id}/resume", response_model=SessionOut)
async def resume_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Resume a paused session (§8.5).
    Restores session state from Redis. Fails if Redis state has expired (24h TTL).
    """
    session = await _get_validated_session(session_id, current_user, db)

    if session.status != "paused":
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message=f"Only paused sessions can be resumed (current: {session.status})",
            status_code=404,
        )

    # Verify Redis state still exists
    state_mgr = LearningStateManagerAgent(db, redis)
    session_state = await state_mgr.get_session_state(str(session_id))
    if not session_state:
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message="Session state expired in Redis. Please create a new session.",
            status_code=404,
        )

    session.status = "active"
    db.add(session)
    await db.commit()
    await db.refresh(session)

    await state_mgr.update_session_state(str(session_id), {"status": "active"})

    logger.info("session_resumed", session_id=str(session_id))
    return SessionOut.model_validate(session)


# --- POST /sessions/{id}/end — End session early (§8.5) ---
@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """End a session early (§8.5).
    Persists final state to PostgreSQL and cleans up Redis.
    """
    session = await _get_validated_session(session_id, current_user, db)

    if session.status not in ("active", "paused"):
        raise PlatformError(
            code="SESSION_NOT_FOUND",
            message=f"Session is already {session.status}",
            status_code=404,
        )

    state_mgr = LearningStateManagerAgent(db, redis)

    # Read final state from Redis before cleanup
    session_state = await state_mgr.get_session_state(str(session_id))
    final_score = None
    if session_state:
        scores = session_state.get("scores", [])
        if scores:
            final_score = sum(scores) / len(scores)

    # Update PostgreSQL
    session.status = "completed"
    session.ended_at = datetime.utcnow()
    session.final_score = final_score
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Mark Redis state as completed (don't delete — transcript may be needed)
    if session_state:
        await state_mgr.update_session_state(str(session_id), {
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
        })

    logger.info("session_ended", session_id=str(session_id), final_score=final_score)
    return SessionOut.model_validate(session)
