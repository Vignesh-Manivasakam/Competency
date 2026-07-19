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
