# app/api/v1/websockets.py
"""WebSocket handler + Session REST routes.

From spec §8.5: Session endpoints for lifecycle management.
From spec §8.8: WebSocket message protocol (Listing 10).
From spec §21.3: Flow 3 — Adaptive Learning Session end-to-end.

WebSocket authentication: JWT passed as query parameter since
browsers don't support Authorization headers on WebSocket upgrades.
  ws://host/api/v1/sessions/{id}/ws?token={jwt}
"""
import asyncio
import json
import time
import uuid
import structlog
from datetime import datetime
from typing import Optional
from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies import get_async_session, get_current_user
from app.core.security import verify_jwt
from jose import JWTError
from app.models.session import LearningSession, ContentItem
from app.models.competency import Skill
from app.models.user import User
from app.services.connection_manager import connection_manager
from app.agents.orchestrator import orchestrator
from app.api.v1.schemas.ws_messages import (
    ClientMessageType,
    TutorMessage,
    ContentDeliveredMessage,
    MasteryUpdatedMessage,
    SessionCompleteMessage,
    ErrorMessage,
    PongMessage,
    SessionPausedMessage,
    SessionResumedMessage,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/sessions", tags=["sessions"])


# ──────────────────────────────────────────────
# Request/Response Schemas (§8.5)
# ──────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    skill_id: str
    competency_id: Optional[str] = None
    preferred_content_type: Optional[str] = None  # explanation|quiz|scenario|dialogue


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str = "created"
    websocket_url: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    skill_id: str
    employee_id: str
    interaction_count: int = 0
    current_score: float = 0.0
    mastery_level: int = 0
    created_at: Optional[datetime] = None
    is_websocket_connected: bool = False


class InteractRequest(BaseModel):
    """HTTP polling fallback for environments where WebSocket is unavailable."""
    content: str = Field(..., min_length=1, max_length=5000)
    response_latency_ms: int = Field(default=0, ge=0)


class InteractResponse(BaseModel):
    tutor_message: str
    next_action: str
    current_score: float
    interaction_count: int
    session_complete: bool = False


class TranscriptMessage(BaseModel):
    role: str  # "employee" | "tutor" | "system"
    content: str
    timestamp: datetime


class TranscriptResponse(BaseModel):
    session_id: str
    messages: list[TranscriptMessage]
    total_count: int


# ──────────────────────────────────────────────
# REST Session Routes (§8.5)
# ──────────────────────────────────────────────

@router.post("", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new learning session.
    
    From §21.3 Step 1:
    POST /sessions with skill_id → creates session row,
    returns session_id and WebSocket URL for frontend to connect.
    """
    try:
        skill_uuid = uuid.UUID(request.skill_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill_id UUID format")

    competency_id = request.competency_id
    if not competency_id:
        skill = await db.get(Skill, skill_uuid)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        competency_id = str(skill.competency_id)

    try:
        comp_uuid = uuid.UUID(competency_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid competency_id UUID format")

    session_id = str(uuid.uuid4())

    session = LearningSession(
        id=uuid.UUID(session_id),
        employee_id=current_user.id,
        skill_id=skill_uuid,
        competency_id=comp_uuid,
        status="active",
        session_type="learning",
        interaction_count=0,
        final_score=0.0,
    )
    db.add(session)
    await db.commit()

    logger.info(
        "session_created",
        session_id=session_id,
        skill_id=request.skill_id,
        employee_id=str(current_user.id),
    )

    return CreateSessionResponse(
        session_id=session_id,
        status="active",
        websocket_url=f"/api/v1/sessions/{session_id}/ws",
    )


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get current session status and metrics."""
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID format")

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    return SessionStatusResponse(
        session_id=str(session.id),
        status=session.status,
        skill_id=str(session.skill_id),
        employee_id=str(session.employee_id),
        interaction_count=session.interaction_count,
        current_score=session.final_score or 0.0,
        mastery_level=0,
        created_at=session.created_at,
        is_websocket_connected=connection_manager.get_connection(session_id) is not None,
    )


@router.post("/{session_id}/interact", response_model=InteractResponse)
async def interact_http(
    session_id: str,
    request: InteractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """HTTP polling fallback for employee response submission.
    
    From §8.5: For environments where WebSocket is unavailable
    (corporate proxies, etc.). Runs one full graph cycle synchronously.
    """
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID format")

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    # Run one interaction cycle through the graph
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    state_updates = {
        "session_id": session_id,
        "employee_id": str(current_user.id),
        "skill_id": str(session.skill_id),
        "messages": [{"role": "user", "content": request.content}],
        "workflow_type": "learning",
    }

    result = await graph.ainvoke(state_updates, config=config)

    tutor_content = result.get("generated_content", {})
    return InteractResponse(
        tutor_message=tutor_content.get("tutor_response", ""),
        next_action=result.get("next_action", "continue"),
        current_score=result.get("current_proficiency", 0.0),
        interaction_count=result.get("interaction_count", 0),
        session_complete=result.get("next_action") in ("COMPLETE", "session_end"),
    )


@router.get("/{session_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get full session message history.
    
    From §8.5: Returns the complete transcript for review,
    compliance, or manager audit.
    """
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID format")

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    # Retrieve transcript from checkpointed graph state
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    try:
        graph_state = await graph.aget_state(config)
        messages = graph_state.values.get("messages", [])
    except Exception:
        messages = []

    transcript = []
    for msg in messages:
        role = "employee" if getattr(msg, "type", "") == "human" else "tutor"
        transcript.append(TranscriptMessage(
            role=role,
            content=getattr(msg, "content", str(msg)),
            timestamp=getattr(msg, "additional_kwargs", {}).get(
                "timestamp", datetime.utcnow()
            ),
        ))

    return TranscriptResponse(
        session_id=session_id,
        messages=transcript,
        total_count=len(transcript),
    )


@router.post("/{session_id}/pause", status_code=200)
async def pause_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Pause an active session."""
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID format")

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    session.status = "paused"
    await db.commit()

    await connection_manager.mark_paused(session_id)
    await connection_manager.send_message(session_id, SessionPausedMessage(
        session_id=session_id,
    ).model_dump(mode="json"))

    return {"status": "paused", "session_id": session_id}


@router.post("/{session_id}/resume", status_code=200)
async def resume_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Resume a paused session."""
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID format")

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    session.status = "active"
    await db.commit()

    await connection_manager.mark_resumed(session_id)
    await connection_manager.send_message(session_id, SessionResumedMessage(
        session_id=session_id,
    ).model_dump(mode="json"))

    return {"status": "active", "session_id": session_id}


@router.post("/{session_id}/end", status_code=200)
async def end_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """End a session early."""
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID format")

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    session.status = "completed"
    session.ended_at = datetime.utcnow()
    await db.commit()

    await connection_manager.send_message(session_id, SessionCompleteMessage(
        final_score=session.final_score or 0.0,
        mastery_level=0,
        mastery_upgraded=False,
        session_summary="Session ended early by employee.",
        total_interactions=session.interaction_count,
    ).model_dump(mode="json"))

    await connection_manager.disconnect(session_id)
    return {"status": "completed", "session_id": session_id}


# ──────────────────────────────────────────────
# WebSocket Handler (§8.8 + §21.3)
# ──────────────────────────────────────────────

async def _authenticate_ws(token: str, db: AsyncSession) -> Optional[User]:
    """Validate JWT from WebSocket query parameter.
    
    WebSocket connections cannot use Authorization headers,
    so the JWT is passed as ?token={jwt} query parameter.
    """
    try:
        payload = verify_jwt(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = await db.get(User, uuid.UUID(user_id))
        return user
    except Exception as e:
        logger.warning("ws_auth_failed", error=str(e))
        return None


@router.websocket("/{session_id}/ws")
async def websocket_session(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_async_session),
):
    """WebSocket endpoint for real-time learning sessions.
    
    From spec §8.8 & §21.3 (Flow 3):
    
    Connection Flow:
    1. Frontend connects: ws://host/api/v1/sessions/{id}/ws?token={jwt}
    2. Server validates JWT from query param
    3. Server registers connection in ConnectionManager
    4. Server runs initial graph cycle (load_state → generate → review → deliver)
    5. Server sends content_delivered message
    6. Client sends employee_response messages
    7. Server runs scoring cycle, sends tutor_message
    8. Loop until session_complete or mastery_upgraded
    
    Error Recovery:
    - On graph execution failure: send error message with retryable=True
    - On auth failure: close with 4003 code
    - On unexpected disconnect: state is checkpointed, session resumable
    """
    # ── Step 1: Authenticate via JWT query parameter ──
    user = await _authenticate_ws(token, db)
    if not user or not user.is_active:
        await websocket.close(code=4003, reason="Authentication failed")
        return

    logger.info(
        "ws_session_starting",
        session_id=session_id,
        employee_id=str(user.id),
    )

    # ── Step 2: Validate session ownership ──
    try:
        sess_uuid = uuid.UUID(session_id)
    except ValueError:
        await websocket.close(code=4000, reason="Invalid session UUID format")
        return

    session = await db.get(LearningSession, sess_uuid)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    if session.employee_id != user.id:
        await websocket.close(code=4003, reason="Not your session")
        return

    # ── Step 3: Register connection ──
    conn_info = await connection_manager.connect(
        websocket=websocket,
        session_id=session_id,
        employee_id=str(user.id),
    )

    session_start_time = time.time()

    try:
        # ── Step 4: Run initial graph cycle ──
        await _run_initial_cycle(session_id, str(user.id), str(session.skill_id), str(session.competency_id))

        # ── Step 5: Message loop ──
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=300.0,  # 5-minute inactivity timeout
                )
            except asyncio.TimeoutError:
                await connection_manager.send_message(
                    session_id,
                    ErrorMessage(
                        code="INACTIVITY_TIMEOUT",
                        message="Session timed out due to inactivity (5 minutes).",
                        retryable=False,
                    ).model_dump(mode="json"),
                )
                break

            # Parse client message
            try:
                data = json.loads(raw)
                msg_type = data.get("type", "")
            except json.JSONDecodeError:
                await connection_manager.send_message(
                    session_id,
                    ErrorMessage(
                        code="INVALID_JSON",
                        message="Message must be valid JSON.",
                        retryable=True,
                    ).model_dump(mode="json"),
                )
                continue

            # ── Handle: ping ──
            if msg_type == ClientMessageType.PING:
                await connection_manager.send_message(
                    session_id,
                    PongMessage().model_dump(mode="json"),
                )
                continue

            # ── Handle: pause_session ──
            if msg_type == ClientMessageType.PAUSE_SESSION:
                await connection_manager.mark_paused(session_id)
                await connection_manager.send_message(
                    session_id,
                    SessionPausedMessage(
                        session_id=session_id,
                    ).model_dump(mode="json"),
                )
                continue

            # ── Handle: employee_response ──
            if msg_type == ClientMessageType.EMPLOYEE_RESPONSE:
                content = data.get("content", "")
                latency_ms = data.get("response_latency_ms", 0)

                if not content or not content.strip():
                    await connection_manager.send_message(
                        session_id,
                        ErrorMessage(
                            code="EMPTY_RESPONSE",
                            message="Response content cannot be empty.",
                            retryable=True,
                        ).model_dump(mode="json"),
                    )
                    continue

                # Check if session is paused
                if conn_info.is_paused:
                    await connection_manager.send_message(
                        session_id,
                        ErrorMessage(
                            code="SESSION_PAUSED",
                            message="Session is paused. Resume before responding.",
                            retryable=True,
                        ).model_dump(mode="json"),
                    )
                    continue

                await connection_manager.increment_interaction(session_id)

                # Update database interaction count
                session.interaction_count += 1
                await db.commit()

                # Run the scoring cycle through the graph
                is_complete = await _run_response_cycle(
                    session_id=session_id,
                    employee_id=str(user.id),
                    skill_id=str(session.skill_id),
                    competency_id=str(session.competency_id),
                    content=content,
                    response_latency_ms=latency_ms,
                    db=db,
                    session_row=session,
                )

                if is_complete:
                    break

                continue

            # ── Unknown message type ──
            await connection_manager.send_message(
                session_id,
                ErrorMessage(
                    code="UNKNOWN_MESSAGE_TYPE",
                    message=f"Unknown message type: {msg_type}",
                    retryable=True,
                ).model_dump(mode="json"),
            )

    except WebSocketDisconnect as e:
        logger.info(
            "ws_client_disconnected",
            session_id=session_id,
            code=e.code,
            reason=getattr(e, "reason", None),
        )
    except Exception as e:
        logger.error(
            "ws_unexpected_error",
            session_id=session_id,
            error=str(e),
        )
        try:
            await connection_manager.send_message(
                session_id,
                ErrorMessage(
                    code="INTERNAL_ERROR",
                    message="An unexpected error occurred. Your progress is saved.",
                    retryable=True,
                ).model_dump(mode="json"),
            )
        except Exception:
            pass
    finally:
        duration = int(time.time() - session_start_time)
        logger.info(
            "ws_session_ended",
            session_id=session_id,
            duration_seconds=duration,
            interactions=conn_info.interaction_count,
        )
        await connection_manager.disconnect(session_id)


# ──────────────────────────────────────────────
# Graph Execution Helpers
# ──────────────────────────────────────────────

async def _run_initial_cycle(
    session_id: str,
    employee_id: str,
    skill_id: str,
    competency_id: str,
):
    """Run the first graph cycle: load → generate → review → deliver."""
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "session_id": session_id,
        "employee_id": employee_id,
        "skill_id": skill_id,
        "competency_id": competency_id,
        "workflow_type": "learning",
        "current_node": "start",
        "next_action": "start",
        "interaction_count": 0,
        "current_proficiency": 0.0,
        "session_scores": [],
        "messages": [],
        "retry_count": 0,
        "fallback_triggered": False,
        "error": None,
    }

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=config),
            timeout=15.0,  # 15s timeout for initial cycle
        )

        content = result.get("generated_content", {})

        # Send content_delivered message
        await connection_manager.send_message(
            session_id,
            ContentDeliveredMessage(
                content_type=content.get("content_type", "explanation"),
                content=content.get("content_body", ""),
                interaction_prompts=content.get("interaction_prompts", []),
                difficulty_level=content.get("difficulty_level", 3),
                module_title=content.get("module_title"),
            ).model_dump(mode="json"),
        )

    except asyncio.TimeoutError:
        logger.error("initial_cycle_timeout", session_id=session_id)
        await connection_manager.send_message(
            session_id,
            ErrorMessage(
                code="GRAPH_TIMEOUT",
                message="Content generation timed out. Please try again.",
                retryable=True,
            ).model_dump(mode="json"),
        )
    except Exception as e:
        logger.error("initial_cycle_error", session_id=session_id, error=str(e))
        await connection_manager.send_message(
            session_id,
            ErrorMessage(
                code="LLM_FAILURE",
                message="Failed to generate initial content. Retrying...",
                retryable=True,
            ).model_dump(mode="json"),
        )


async def _run_response_cycle(
    session_id: str,
    employee_id: str,
    skill_id: str,
    competency_id: str,
    content: str,
    response_latency_ms: int,
    db: AsyncSession,
    session_row: LearningSession,
) -> bool:
    """Run the scoring cycle after employee responds."""
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    # Update state with employee response
    state_updates = {
        "session_id": session_id,
        "employee_id": employee_id,
        "skill_id": skill_id,
        "competency_id": competency_id,
        "workflow_type": "learning",
        "messages": [{"role": "user", "content": content}],
        "generated_content": {
            "employee_response": content,
            "response_latency_ms": response_latency_ms,
        },
    }

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(state_updates, config=config),
            timeout=20.0,  # 20s timeout for response cycle
        )
    except asyncio.TimeoutError:
        await connection_manager.send_message(
            session_id,
            ErrorMessage(
                code="GRAPH_TIMEOUT",
                message="Response processing timed out. Your answer was saved.",
                retryable=True,
            ).model_dump(mode="json"),
        )
        return False
    except Exception as e:
        logger.error("response_cycle_error", session_id=session_id, error=str(e))
        await connection_manager.send_message(
            session_id,
            ErrorMessage(
                code="LLM_FAILURE",
                message="Error processing your response. Please try again.",
                retryable=True,
            ).model_dump(mode="json"),
        )
        return False

    # Sync state changes back to database session row
    current_prof = result.get("current_proficiency", 0.0)
    session_row.final_score = current_prof
    
    mastery_decision = result.get("mastery_decision", {})
    if mastery_decision and mastery_decision.get("mastery_decision") == "UPGRADE":
        session_row.mastery_reached = True
        
    await db.commit()

    # Check for mastery upgrade (§21.3 Step 8)
    if mastery_decision and mastery_decision.get("mastery_decision") == "UPGRADE":
        old_level = mastery_decision.get("old_mastery_level", 0)
        new_level = mastery_decision.get("new_mastery_level", old_level + 1)

        await connection_manager.send_message(
            session_id,
            MasteryUpdatedMessage(
                skill_id=result.get("skill_id", ""),
                old_level=old_level,
                new_level=new_level,
                evidence_summary=mastery_decision.get("evidence_summary", ""),
            ).model_dump(mode="json"),
        )

    # Check if session is complete
    next_action = result.get("next_action", "continue")
    is_complete = next_action in ("COMPLETE", "complete", "session_end", "upgrade")

    if is_complete:
        session_row.status = "completed"
        session_row.ended_at = datetime.utcnow()
        await db.commit()

        # Send session_complete message
        await connection_manager.send_message(
            session_id,
            SessionCompleteMessage(
                final_score=current_prof,
                mastery_level=mastery_decision.get("new_mastery_level", 0) if mastery_decision else 0,
                mastery_upgraded=mastery_decision.get("mastery_decision") == "UPGRADE" if mastery_decision else False,
                session_summary=_build_session_summary(result),
                total_interactions=result.get("interaction_count", 0),
            ).model_dump(mode="json"),
        )
        return True

    # Session continues — send tutor_message + next content_delivered
    tutor_content = result.get("generated_content", {})

    await connection_manager.send_message(
        session_id,
        TutorMessage(
            content=tutor_content.get("tutor_response", ""),
            next_action=next_action,
            current_score=current_prof,
            interaction_count=result.get("interaction_count", 0),
            mastery_level=mastery_decision.get("new_mastery_level", 0)
                if mastery_decision else 0,
            session_complete=False,
        ).model_dump(mode="json"),
    )

    # If new content was generated (continue/reinforce cycles), deliver it
    if tutor_content.get("content_body"):
        await connection_manager.send_message(
            session_id,
            ContentDeliveredMessage(
                content_type=tutor_content.get("content_type", "explanation"),
                content=tutor_content.get("content_body", ""),
                interaction_prompts=tutor_content.get("interaction_prompts", []),
                difficulty_level=tutor_content.get("difficulty_level", 3),
                module_title=tutor_content.get("module_title"),
            ).model_dump(mode="json"),
        )

    return False


def _build_session_summary(final_state: dict) -> str:
    """Build a human-readable session summary from final graph state."""
    interactions = final_state.get("interaction_count", 0)
    score = final_state.get("current_proficiency", 0.0)
    mastery = final_state.get("mastery_decision", {})
    decision = mastery.get("mastery_decision", "MAINTAIN") if isinstance(mastery, dict) else "MAINTAIN"

    summary_parts = [
        f"Session completed after {interactions} interactions.",
        f"Final score: {score:.1f}/100.",
    ]

    if decision == "UPGRADE" and isinstance(mastery, dict):
        new_level = mastery.get("new_mastery_level", 0)
        level_names = ["Not Started", "Awareness", "Developing",
                       "Proficient", "Advanced", "Mastered"]
        summary_parts.append(
            f"Mastery upgraded to Level {new_level} ({level_names[new_level]})!"
        )
    elif decision == "MAINTAIN" and isinstance(mastery, dict):
        gaps = mastery.get("remaining_gaps", [])
        if gaps:
            summary_parts.append(f"Areas to focus on: {', '.join(gaps[:3])}.")

    return " ".join(summary_parts)
