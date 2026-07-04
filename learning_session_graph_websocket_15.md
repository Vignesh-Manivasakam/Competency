# Learning Session Graph + WebSocket Handler + Message Protocol

## Plan 15 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the full LangGraph learning session graph (`build_learning_session_graph`) that orchestrates the complete adaptive learning loop — from loading employee state through content generation, review, Socratic tutoring, scoring, state updates, and mastery checks. Wire this graph to a FastAPI WebSocket endpoint (`/sessions/{id}/ws`) with JWT authentication, a structured message protocol (§8.8), and a connection manager for tracking active sessions in real time.

### Prerequisites

- **Plan 5** (LangGraph Orchestrator) — `BaseAgent`, `AgentState`, PostgreSQL checkpointer, `Orchestrator` class
- **Plan 12** (Learning Path Designer) — `design_path_node`, `LearningPathOutput` for module selection
- **Plan 13** (Adaptive Tutor) — `prepare_interaction_node`, Socratic dialogue session management
- **Plan 14** (Mastery Evaluation) — `check_mastery_node`, evidence-based mastery decisions

### Spec References

| Section | Content |
|---------|---------|
| §4.2 | Learning Session Graph (Listing 2) — full graph topology with all nodes and edges |
| §8.5 | Session HTTP endpoints — REST fallback routes for session lifecycle |
| §8.8 | WebSocket Message Protocol (Listing 10) — all client↔server message types |
| §21.3 | Flow 3: Adaptive Learning Session — end-to-end 8-step session flow |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── graphs/
│   └── learning_session.py        # Full session graph replacing stub from Plan 5
├── api/v1/
│   ├── websockets.py              # WebSocket handler with JWT auth + session routes
│   └── schemas/
│       └── ws_messages.py         # WebSocket message protocol Pydantic models
└── services/
    └── connection_manager.py      # Active WebSocket connection tracker
```

---

### Detailed Implementation Steps

#### Step 1: WebSocket Message Protocol (from §8.8 Listing 10)

```python
# app/api/v1/schemas/ws_messages.py
"""WebSocket message protocol — all client↔server message types.

From spec §8.8 (Listing 10):
Defines the structured JSON message protocol for real-time
communication between the frontend and the learning session graph.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


# ──────────────────────────────────────────────
# Client → Server Messages
# ──────────────────────────────────────────────

class ClientMessageType(str, Enum):
    EMPLOYEE_RESPONSE = "employee_response"
    PING = "ping"
    PAUSE_SESSION = "pause_session"


class EmployeeResponseMessage(BaseModel):
    """Client sends employee's answer/response to tutor content.
    
    From §8.8: Includes response_latency_ms for engagement
    signal — fast responses may indicate guessing, slow ones
    may indicate deep thinking or confusion.
    """
    type: Literal["employee_response"] = "employee_response"
    session_id: str
    content: str = Field(..., min_length=1, max_length=5000)
    response_latency_ms: int = Field(
        ..., ge=0, le=600_000,
        description="Time in ms between content delivery and response"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PingMessage(BaseModel):
    """Client keepalive — server replies with pong."""
    type: Literal["ping"] = "ping"


class PauseSessionMessage(BaseModel):
    """Client requests session pause (e.g., user stepped away)."""
    type: Literal["pause_session"] = "pause_session"
    session_id: str
    reason: Optional[str] = None


class ClientMessage(BaseModel):
    """Union discriminator for all client messages."""
    type: ClientMessageType
    session_id: Optional[str] = None
    content: Optional[str] = None
    response_latency_ms: Optional[int] = None
    timestamp: Optional[datetime] = None
    reason: Optional[str] = None


# ──────────────────────────────────────────────
# Server → Client Messages
# ──────────────────────────────────────────────

class ServerMessageType(str, Enum):
    TUTOR_MESSAGE = "tutor_message"
    CONTENT_DELIVERED = "content_delivered"
    MASTERY_UPDATED = "mastery_updated"
    SESSION_COMPLETE = "session_complete"
    ERROR = "error"
    PONG = "pong"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"


class TutorMessage(BaseModel):
    """Server sends tutor's Socratic response after scoring.
    
    From §8.8 & §21.3 Step 6:
    Sent after Assessment Scoring evaluates the employee response
    and the Adaptive Tutor generates its next Socratic message.
    """
    type: Literal["tutor_message"] = "tutor_message"
    content: str
    next_action: str  # CONTINUE | REINFORCE | ADVANCE | COMPLETE | ESCALATE
    current_score: float = Field(ge=0.0, le=100.0)
    interaction_count: int = Field(ge=0)
    mastery_level: int = Field(ge=0, le=5)
    session_complete: bool = False


class ContentDeliveredMessage(BaseModel):
    """Server delivers generated & reviewed learning content.
    
    From §8.8 & §21.3 Step 4:
    Sent after Content Generator generates content and
    Content Reviewer approves it.
    """
    type: Literal["content_delivered"] = "content_delivered"
    content_type: str  # explanation | quiz | scenario | dialogue
    content: str
    interaction_prompts: list[str] = Field(
        default_factory=list,
        description="Suggested questions/prompts the employee can respond to"
    )
    difficulty_level: int = Field(ge=1, le=5, default=3)
    module_title: Optional[str] = None


class MasteryUpdatedMessage(BaseModel):
    """Server notifies of mastery level change.
    
    From §8.8 & §21.3 Step 8:
    Sent when Mastery Evaluation Agent decides to upgrade
    (or downgrade) and the competency matrix is updated.
    """
    type: Literal["mastery_updated"] = "mastery_updated"
    skill_id: str
    old_level: int = Field(ge=0, le=5)
    new_level: int = Field(ge=0, le=5)
    evidence_summary: str


class SessionCompleteMessage(BaseModel):
    """Server signals session end — normal completion or mastery reached.
    
    From §8.8 & §21.3 Step 7:
    Sent when session loop ends due to mastery threshold,
    max interactions, or explicit session end.
    """
    type: Literal["session_complete"] = "session_complete"
    final_score: float = Field(ge=0.0, le=100.0)
    mastery_level: int = Field(ge=0, le=5)
    mastery_upgraded: bool = False
    session_summary: str
    total_interactions: int = 0
    duration_seconds: int = 0


class ErrorMessage(BaseModel):
    """Server sends error with retry guidance.
    
    From §8.8: retryable flag tells frontend whether
    to allow automatic retry or show an error screen.
    """
    type: Literal["error"] = "error"
    code: str  # e.g., "GRAPH_TIMEOUT", "LLM_FAILURE", "AUTH_EXPIRED"
    message: str
    retryable: bool = True


class PongMessage(BaseModel):
    """Server keepalive reply."""
    type: Literal["pong"] = "pong"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionPausedMessage(BaseModel):
    """Server confirms session pause."""
    type: Literal["session_paused"] = "session_paused"
    session_id: str
    paused_at: datetime = Field(default_factory=datetime.utcnow)


class SessionResumedMessage(BaseModel):
    """Server confirms session resume."""
    type: Literal["session_resumed"] = "session_resumed"
    session_id: str
    resumed_at: datetime = Field(default_factory=datetime.utcnow)
```

#### Step 2: WebSocket Connection Manager

```python
# app/services/connection_manager.py
"""WebSocket connection manager — tracks all active learning sessions.

Manages the lifecycle of WebSocket connections:
- Register/unregister connections by session_id
- Send messages to specific sessions
- Broadcast to all connections (admin/system messages)
- Track connection metadata (employee_id, connected_at)
- Enforce one-connection-per-session invariant
"""
import asyncio
import structlog
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from fastapi import WebSocket

logger = structlog.get_logger()


@dataclass
class ConnectionInfo:
    """Metadata for an active WebSocket connection."""
    websocket: WebSocket
    session_id: str
    employee_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    is_paused: bool = False
    interaction_count: int = 0


class ConnectionManager:
    """Manages active WebSocket connections for learning sessions.
    
    Thread-safe via asyncio lock. Enforces one WebSocket connection
    per session_id — reconnection replaces the previous connection.
    """

    def __init__(self):
        self._connections: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        employee_id: str,
    ) -> ConnectionInfo:
        """Accept and register a WebSocket connection.
        
        If a connection already exists for this session_id,
        close the old one first (handles browser refresh/reconnect).
        """
        await websocket.accept()

        async with self._lock:
            # Close existing connection for this session (reconnect scenario)
            if session_id in self._connections:
                old_conn = self._connections[session_id]
                try:
                    await old_conn.websocket.close(
                        code=4001,
                        reason="Replaced by new connection"
                    )
                except Exception:
                    pass  # Old connection may already be dead
                logger.info(
                    "ws_connection_replaced",
                    session_id=session_id,
                )

            conn_info = ConnectionInfo(
                websocket=websocket,
                session_id=session_id,
                employee_id=employee_id,
            )
            self._connections[session_id] = conn_info

        logger.info(
            "ws_connected",
            session_id=session_id,
            employee_id=employee_id,
            active_connections=len(self._connections),
        )
        return conn_info

    async def disconnect(self, session_id: str):
        """Unregister a WebSocket connection."""
        async with self._lock:
            conn = self._connections.pop(session_id, None)

        if conn:
            logger.info(
                "ws_disconnected",
                session_id=session_id,
                employee_id=conn.employee_id,
                duration_seconds=(
                    datetime.utcnow() - conn.connected_at
                ).total_seconds(),
                interactions=conn.interaction_count,
                active_connections=len(self._connections),
            )

    async def send_message(self, session_id: str, message: dict) -> bool:
        """Send a JSON message to a specific session's WebSocket.
        
        Returns True if sent successfully, False if connection not found
        or send failed.
        """
        conn = self._connections.get(session_id)
        if not conn:
            logger.warning("ws_send_no_connection", session_id=session_id)
            return False

        try:
            await conn.websocket.send_json(message)
            conn.last_activity = datetime.utcnow()
            return True
        except Exception as e:
            logger.error(
                "ws_send_failed",
                session_id=session_id,
                error=str(e),
            )
            await self.disconnect(session_id)
            return False

    async def broadcast(self, message: dict):
        """Send a message to all active connections (admin use)."""
        disconnected = []
        for session_id, conn in self._connections.items():
            try:
                await conn.websocket.send_json(message)
            except Exception:
                disconnected.append(session_id)

        for sid in disconnected:
            await self.disconnect(sid)

    def get_connection(self, session_id: str) -> Optional[ConnectionInfo]:
        """Get connection info for a session."""
        return self._connections.get(session_id)

    def get_active_count(self) -> int:
        """Number of currently active WebSocket connections."""
        return len(self._connections)

    def get_active_sessions(self) -> list[str]:
        """List all session_ids with active connections."""
        return list(self._connections.keys())

    async def mark_paused(self, session_id: str):
        """Mark a session as paused."""
        conn = self._connections.get(session_id)
        if conn:
            conn.is_paused = True

    async def mark_resumed(self, session_id: str):
        """Mark a session as resumed."""
        conn = self._connections.get(session_id)
        if conn:
            conn.is_paused = False

    async def increment_interaction(self, session_id: str):
        """Increment the interaction counter for tracking."""
        conn = self._connections.get(session_id)
        if conn:
            conn.interaction_count += 1
            conn.last_activity = datetime.utcnow()


# Global singleton — imported by WebSocket handler and session routes
connection_manager = ConnectionManager()
```

#### Step 3: Learning Session Graph (from §4.2 Listing 2 — Replace Stub)

```python
# app/graphs/learning_session.py
"""Learning Session LangGraph — the core adaptive learning loop.

From spec §4.2 (Listing 2):
Implements the full learning session workflow:
  load_state → generate_content → review_content → deliver_to_tutor
  → [wait for employee response] → score_response → update_state
  → check_mastery → [route: upgrade/continue/session_end]

From spec §21.3 (Flow 3):
1. POST /sessions creates session → returns session_id
2. Frontend connects WebSocket /sessions/{id}/ws?token={jwt}
3. LangGraph loads employee state; Path Designer selects module
4. Content Generator generates; Reviewer approves
5. Employee responds via WebSocket
6. Assessment Scoring evaluates; state updated
7. Loop until session_complete or mastery threshold
8. On mastery upgrade: mastery_updated event sent

Graph Topology:
  load_state ──→ generate_content ──→ review_content ──→[route_after_review]
                                         ├─ APPROVE → deliver_to_tutor
                                         ├─ REVISE  → generate_content (loop)
                                         └─ ERROR   → handle_error

  deliver_to_tutor ──→ score_response ──→ update_state ──→[route_after_score]
                                            ├─ continue     → generate_content
                                            ├─ reinforce    → generate_content
                                            ├─ check_mastery→ check_mastery
                                            └─ session_end  → END

  check_mastery ──→[route_after_mastery]
                     ├─ upgrade     → END (with mastery_updated event)
                     ├─ continue    → generate_content
                     └─ session_end → END
"""
import structlog
from langgraph.graph import StateGraph, END
from langgraph.graph.graph import CompiledGraph
from app.graphs.state import AgentState

# Import agent node functions from their respective plans
from app.agents.learning_path_designer import design_path_node
from app.agents.content_generator import generate_content_node
from app.agents.content_reviewer import review_content_node
from app.agents.adaptive_tutor import prepare_interaction_node
from app.agents.assessment_scoring import score_response_node
from app.agents.mastery_evaluation import check_mastery_node
from app.agents.learning_state_manager import (
    load_state_node,
    update_state_node,
)
from app.graphs.error_handler import handle_error

logger = structlog.get_logger()

# ──────────────────────────────────────────────
# Maximum limits (safety bounds)
# ──────────────────────────────────────────────
MAX_INTERACTIONS_PER_SESSION = 25
MAX_CONTENT_REVISIONS = 3
MASTERY_CHECK_INTERVAL = 5  # Check mastery every N interactions


# ──────────────────────────────────────────────
# Routing Functions
# ──────────────────────────────────────────────

def route_after_review(state: AgentState) -> str:
    """Route after Content Reviewer evaluates generated content.
    
    From §4.2: Three possible outcomes:
    - APPROVE: Content quality passes → deliver to tutor
    - REVISE:  Content needs improvement → loop back to generator
    - ERROR:   Review failed entirely → error handler
    
    Safety: Caps revision loops at MAX_CONTENT_REVISIONS to prevent
    infinite generate→review→revise loops.
    """
    review_result = state.get("generated_content", {}).get("review_result", {})
    review_decision = review_result.get("decision", "APPROVE")
    revision_count = state.get("generated_content", {}).get("revision_count", 0)
    error = state.get("error")

    if error:
        logger.warning("route_after_review_error", error=error)
        return "ERROR"

    if review_decision == "REVISE" and revision_count < MAX_CONTENT_REVISIONS:
        logger.info(
            "content_revision_requested",
            revision_count=revision_count + 1,
            max_revisions=MAX_CONTENT_REVISIONS,
        )
        return "REVISE"

    if review_decision == "REVISE" and revision_count >= MAX_CONTENT_REVISIONS:
        logger.warning(
            "content_revision_limit_reached",
            revision_count=revision_count,
        )
        # Accept the content as-is after max revisions
        return "APPROVE"

    return "APPROVE"


def route_after_score(state: AgentState) -> str:
    """Route after Assessment Scoring and state update.
    
    From §4.2: Determines the next loop action based on
    tutor's decision and interaction count:
    - continue:      Keep going with new content
    - reinforce:     Same topic, different angle (difficulty -1)
    - check_mastery: Enough evidence to evaluate mastery upgrade
    - session_end:   Max interactions reached or COMPLETE action
    """
    next_action = state.get("next_action", "continue")
    interaction_count = state.get("interaction_count", 0)
    error = state.get("error")

    if error:
        return "session_end"

    # Check if max interactions reached
    if interaction_count >= MAX_INTERACTIONS_PER_SESSION:
        logger.info(
            "max_interactions_reached",
            count=interaction_count,
            max=MAX_INTERACTIONS_PER_SESSION,
        )
        return "check_mastery"

    # Tutor decided session is complete
    if next_action in ("COMPLETE", "complete"):
        return "check_mastery"

    # Periodic mastery check
    if (interaction_count > 0
            and interaction_count % MASTERY_CHECK_INTERVAL == 0):
        return "check_mastery"

    # Escalation → end session, flag for human review
    if next_action in ("ESCALATE", "escalate"):
        return "session_end"

    # CONTINUE, REINFORCE, ADVANCE all generate new content
    if next_action in ("REINFORCE", "reinforce"):
        return "reinforce"

    return "continue"


def route_after_mastery(state: AgentState) -> str:
    """Route after Mastery Evaluation Agent decision.
    
    From §4.2: Three outcomes:
    - upgrade:     Mastery upgraded → end session (celebration!)
    - continue:    Not ready for upgrade → keep learning
    - session_end: Downgrade or session should end
    """
    mastery_decision = state.get("mastery_decision", {})
    decision = mastery_decision.get("mastery_decision", "MAINTAIN")
    interaction_count = state.get("interaction_count", 0)

    if decision == "UPGRADE":
        logger.info(
            "mastery_upgrade_routed",
            new_level=mastery_decision.get("new_mastery_level"),
            confidence=mastery_decision.get("confidence"),
        )
        return "upgrade"

    if decision == "DOWNGRADE":
        return "session_end"

    # MAINTAIN — keep learning if under interaction limit
    if interaction_count < MAX_INTERACTIONS_PER_SESSION:
        return "continue"

    return "session_end"


# ──────────────────────────────────────────────
# Graph Builder
# ──────────────────────────────────────────────

def build_learning_session_graph(checkpointer) -> CompiledGraph:
    """Build the full Learning Session LangGraph.
    
    From spec §4.2 (Listing 2):
    This is the primary workflow graph that drives every adaptive
    learning session. It connects all 7 agent node functions in
    the correct topology with conditional routing edges.
    
    Args:
        checkpointer: AsyncPostgresSaver from Plan 5 — enables
                      session resume after crashes, full audit trail,
                      and time-travel debugging.
    
    Returns:
        CompiledGraph ready for ainvoke() with thread_id checkpointing.
    """
    graph = StateGraph(AgentState)

    # ── Register all nodes (from §4.2 Listing 2) ──
    graph.add_node("load_state", load_state_node)
    graph.add_node("generate_content", generate_content_node)
    graph.add_node("review_content", review_content_node)
    graph.add_node("deliver_to_tutor", prepare_interaction_node)
    graph.add_node("score_response", score_response_node)
    graph.add_node("update_state", update_state_node)
    graph.add_node("check_mastery", check_mastery_node)
    graph.add_node("handle_error", handle_error)

    # ── Entry point ──
    graph.set_entry_point("load_state")

    # ── Linear edges ──
    graph.add_edge("load_state", "generate_content")
    graph.add_edge("generate_content", "review_content")
    graph.add_edge("deliver_to_tutor", "score_response")
    graph.add_edge("score_response", "update_state")

    # ── Conditional edge: after review ──
    graph.add_conditional_edges(
        "review_content",
        route_after_review,
        {
            "APPROVE": "deliver_to_tutor",
            "REVISE": "generate_content",   # Loop back for revision
            "ERROR": "handle_error",
        },
    )

    # ── Conditional edge: after score + state update ──
    graph.add_conditional_edges(
        "update_state",
        route_after_score,
        {
            "continue": "generate_content",
            "reinforce": "generate_content",
            "check_mastery": "check_mastery",
            "session_end": END,
        },
    )

    # ── Conditional edge: after mastery check ──
    graph.add_conditional_edges(
        "check_mastery",
        route_after_mastery,
        {
            "upgrade": END,
            "continue": "generate_content",
            "session_end": END,
        },
    )

    # ── Error handler always terminates ──
    graph.add_edge("handle_error", END)

    logger.info("learning_session_graph_compiled")
    return graph.compile(checkpointer=checkpointer)
```

#### Step 4: WebSocket Handler + Session REST Routes (from §8.5 & §8.8)

```python
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
import structlog
from datetime import datetime
from uuid import uuid4
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
from typing import Optional
from sqlmodel import Session, select

from app.core.deps import get_db, get_current_user
from app.core.security import decode_access_token
from app.models.session import LearningSession, SessionStatus
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
    created_at: datetime
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
    db: Session = Depends(get_db),
):
    """Create a new learning session.
    
    From §21.3 Step 1:
    POST /sessions with skill_id → creates session row,
    returns session_id and WebSocket URL for frontend to connect.
    """
    session_id = str(uuid4())

    session = LearningSession(
        id=session_id,
        employee_id=str(current_user.id),
        skill_id=request.skill_id,
        competency_id=request.competency_id,
        status=SessionStatus.CREATED,
        interaction_count=0,
        current_score=0.0,
    )
    db.add(session)
    db.commit()

    logger.info(
        "session_created",
        session_id=session_id,
        skill_id=request.skill_id,
        employee_id=str(current_user.id),
    )

    return CreateSessionResponse(
        session_id=session_id,
        status="created",
        websocket_url=f"/api/v1/sessions/{session_id}/ws",
    )


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current session status and metrics."""
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your session")

    return SessionStatusResponse(
        session_id=session.id,
        status=session.status.value,
        skill_id=session.skill_id,
        employee_id=session.employee_id,
        interaction_count=session.interaction_count,
        current_score=session.current_score,
        mastery_level=session.mastery_level or 0,
        created_at=session.created_at,
        is_websocket_connected=connection_manager.get_connection(session_id) is not None,
    )


@router.post("/{session_id}/interact", response_model=InteractResponse)
async def interact_http(
    session_id: str,
    request: InteractRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """HTTP polling fallback for employee response submission.
    
    From §8.5: For environments where WebSocket is unavailable
    (corporate proxies, etc.). Runs one full graph cycle synchronously.
    """
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your session")

    # Run one interaction cycle through the graph
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    state_updates = {
        "session_id": session_id,
        "employee_id": str(current_user.id),
        "skill_id": session.skill_id,
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
    db: Session = Depends(get_db),
):
    """Get full session message history.
    
    From §8.5: Returns the complete transcript for review,
    compliance, or manager audit.
    """
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != str(current_user.id):
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
    db: Session = Depends(get_db),
):
    """Pause an active session."""
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your session")

    session.status = SessionStatus.PAUSED
    db.commit()

    await connection_manager.mark_paused(session_id)
    await connection_manager.send_message(session_id, SessionPausedMessage(
        session_id=session_id,
    ).model_dump(mode="json"))

    return {"status": "paused", "session_id": session_id}


@router.post("/{session_id}/resume", status_code=200)
async def resume_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resume a paused session."""
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your session")

    session.status = SessionStatus.ACTIVE
    db.commit()

    await connection_manager.mark_resumed(session_id)
    await connection_manager.send_message(session_id, SessionResumedMessage(
        session_id=session_id,
    ).model_dump(mode="json"))

    return {"status": "active", "session_id": session_id}


@router.post("/{session_id}/end", status_code=200)
async def end_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """End a session early."""
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.employee_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your session")

    session.status = SessionStatus.COMPLETED
    session.ended_at = datetime.utcnow()
    db.commit()

    # Send session_complete via WebSocket if connected
    await connection_manager.send_message(session_id, SessionCompleteMessage(
        final_score=session.current_score,
        mastery_level=session.mastery_level or 0,
        mastery_upgraded=False,
        session_summary="Session ended early by employee.",
        total_interactions=session.interaction_count,
    ).model_dump(mode="json"))

    await connection_manager.disconnect(session_id)
    return {"status": "completed", "session_id": session_id}


# ──────────────────────────────────────────────
# WebSocket Handler (§8.8 + §21.3)
# ──────────────────────────────────────────────

async def _authenticate_ws(token: str) -> Optional[User]:
    """Validate JWT from WebSocket query parameter.
    
    WebSocket connections cannot use Authorization headers,
    so the JWT is passed as ?token={jwt} query parameter.
    """
    try:
        payload = decode_access_token(token)
        if payload is None:
            return None
        # Fetch user from payload (employee_id / sub)
        user_id = payload.get("sub")
        if not user_id:
            return None
        # Return a minimal User object for WS context
        return User(id=user_id, email=payload.get("email", ""))
    except Exception as e:
        logger.warning("ws_auth_failed", error=str(e))
        return None


@router.websocket("/{session_id}/ws")
async def websocket_session(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
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
    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4003, reason="Authentication failed")
        return

    # ── Step 2: Validate session ownership ──
    # (In production, use async DB session; simplified here)
    logger.info(
        "ws_session_starting",
        session_id=session_id,
        employee_id=str(user.id),
    )

    # ── Step 3: Register connection ──
    conn_info = await connection_manager.connect(
        websocket=websocket,
        session_id=session_id,
        employee_id=str(user.id),
    )

    session_start_time = time.time()

    try:
        # ── Step 4: Run initial graph cycle ──
        # From §21.3 Steps 3-4:
        # LangGraph loads employee state → Path Designer selects module →
        # Content Generator generates → Reviewer approves →
        # Server sends content_delivered
        await _run_initial_cycle(session_id, str(user.id), websocket)

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

                # From §21.3 Steps 5-7:
                # Run the scoring cycle through the graph
                is_complete = await _run_response_cycle(
                    session_id=session_id,
                    employee_id=str(user.id),
                    content=content,
                    response_latency_ms=latency_ms,
                    websocket=websocket,
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
    websocket: WebSocket,
):
    """Run the first graph cycle: load → generate → review → deliver.
    
    From §21.3 Steps 3-4:
    Executes the graph up to the deliver_to_tutor node, then
    sends the content_delivered WebSocket message to the client.
    
    Target: First message delivered within 4 seconds (§21.3).
    """
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "session_id": session_id,
        "employee_id": employee_id,
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
    content: str,
    response_latency_ms: int,
    websocket: WebSocket,
) -> bool:
    """Run the scoring cycle after employee responds.
    
    From §21.3 Steps 5-7:
    score_response → update_state → [route] → generate_content → review → deliver
    
    Returns True if session is complete, False to continue.
    """
    graph = orchestrator.get_graph("learning")
    config = {"configurable": {"thread_id": session_id}}

    # Update state with employee response
    state_updates = {
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

    # Check for mastery upgrade (§21.3 Step 8)
    mastery_decision = result.get("mastery_decision", {})
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
        # Send session_complete message
        await connection_manager.send_message(
            session_id,
            SessionCompleteMessage(
                final_score=result.get("current_proficiency", 0.0),
                mastery_level=mastery_decision.get("new_mastery_level", 0),
                mastery_upgraded=mastery_decision.get("mastery_decision") == "UPGRADE",
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
            current_score=result.get("current_proficiency", 0.0),
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
    decision = mastery.get("mastery_decision", "MAINTAIN")

    summary_parts = [
        f"Session completed after {interactions} interactions.",
        f"Final score: {score:.1f}/100.",
    ]

    if decision == "UPGRADE":
        new_level = mastery.get("new_mastery_level", 0)
        level_names = ["Not Started", "Awareness", "Developing",
                       "Proficient", "Advanced", "Mastered"]
        summary_parts.append(
            f"Mastery upgraded to Level {new_level} ({level_names[new_level]})!"
        )
    elif decision == "MAINTAIN":
        gaps = mastery.get("remaining_gaps", [])
        if gaps:
            summary_parts.append(f"Areas to focus on: {', '.join(gaps[:3])}.")

    return " ".join(summary_parts)
```

---

### Verification Criteria

1. **Full 5-turn session via WebSocket**: Connect → receive `content_delivered` → send 5 `employee_response` messages → receive 5 `tutor_message` replies → graph state accumulates correctly across all turns
2. **Routing correctness**: `route_after_review` returns APPROVE/REVISE/ERROR; `route_after_score` returns continue/reinforce/check_mastery/session_end; `route_after_mastery` returns upgrade/continue/session_end — each tested with representative state dicts
3. **First message under 4 seconds**: Initial cycle (load → generate → review → deliver) completes and sends `content_delivered` within the §21.3 latency target; 15-second timeout as safety net
4. **Mastery upgrade event delivery**: When mastery evaluation returns UPGRADE, both `mastery_updated` and `session_complete` (with `mastery_upgraded=true`) are sent to the client in order
5. **Error recovery**: LLM failure during graph execution → `error` message with `retryable=true` sent to client; graph state checkpointed and resumable via WebSocket reconnect or HTTP `/interact` fallback
6. **JWT auth enforcement**: WebSocket connection without `?token=` or with invalid/expired JWT → immediate close with code 4003
7. **Connection manager invariants**: One connection per session; browser refresh replaces old connection (code 4001); disconnect cleans up; `get_active_count()` accurate
8. **HTTP polling fallback**: `POST /sessions/{id}/interact` executes one full graph cycle and returns `InteractResponse` with tutor message
9. **Session lifecycle**: create → active → pause → resume → end all update status correctly and send appropriate WebSocket messages
10. **Content revision loop safety**: `route_after_review` caps revision loops at `MAX_CONTENT_REVISIONS=3` — no infinite generate→review→revise cycles

### Notes & Gotchas

- **WebSocket JWT via query param**: Browsers don't support `Authorization` headers on WebSocket upgrades — the JWT must be passed as `?token={jwt}`. This is standard practice but means tokens appear in server access logs; ensure logs are scrubbed in production
- **Checkpointer enables resume**: If the WebSocket disconnects mid-session (network drop, browser crash), the PostgreSQL checkpointer preserves the exact graph state. The employee can reconnect and the graph resumes from the last completed node — no progress lost
- **`ainvoke` vs `astream`**: This plan uses `ainvoke` for simplicity (waits for full cycle completion). Plan 20 (Performance) can upgrade to `astream` for token-level streaming of tutor responses for better perceived latency
- **Inactivity timeout**: 5-minute timeout on `receive_text()` prevents zombie connections. Frontend should implement ping every 30 seconds to keep the connection alive
- **ConnectionManager is in-process**: The singleton `connection_manager` only tracks connections in the current process. For multi-process deployments (Plan 20), upgrade to Redis pub/sub for cross-process WebSocket routing
- **Graph interrupt for human input**: The graph runs a full cycle per employee response. Between cycles, the graph is checkpointed and the WebSocket handler waits for the next `employee_response` message — this is the "human-in-the-loop" pattern from LangGraph
- **MAX_INTERACTIONS_PER_SESSION = 25**: Safety bound to prevent infinite sessions. Configurable per deployment; set conservatively for MVP to cap LLM costs
- **Revision loop cap**: `MAX_CONTENT_REVISIONS = 3` prevents the Content Reviewer from infinitely requesting rewrites — after 3 revisions, content is accepted as-is
