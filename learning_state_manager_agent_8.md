# Learning State Manager Agent

## Plan 8 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the Learning State Manager Agent — the central state operations hub. All other agents request state through this agent (no direct DB calls). Covers Redis session state, PostgreSQL persistent state, mastery history commits, competency matrix computation, and all Redis key patterns from the spec's four-tier memory model.

### Prerequisites

- **Plan 1** (Infrastructure) — Redis running
- **Plan 2** (Database Schema) — EmployeeLearningState, MasteryHistory tables
- **Plan 5** (LangGraph Orchestrator) — BaseAgent class

### Spec References

| Section | Content |
|---------|---------|
| §3 Learning State Manager Agent | Operations, storage mapping, concurrency |
| §5.1 Four-Tier Memory Model | Tier 2 (Redis), Tier 3 (PostgreSQL) |
| §5.2 Redis Key Schema | All 7 key patterns with TTLs |
| §7 Pydantic Schemas | LearningStateOut, CompetencyMatrixOut, SkillMatrixEntry |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── agents/
│   └── learning_state_manager.py   # Agent implementation
├── core/
│   └── redis.py                    # Redis client (update with operations)
└── schemas/
    └── learning_state.py           # Pydantic models
```

---

### Detailed Implementation Steps

#### Step 1: Pydantic Schemas

```python
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
```

#### Step 2: Agent Implementation

```python
# app/agents/learning_state_manager.py
"""Learning State Manager Agent — all state read/write operations.

From spec §3:
Role: Single agent responsible for all state read/write operations.
All other agents request state through this agent (no direct DB calls).
LLM: None (pure data operations; deterministic)

Operations:
- get_learning_state(employee_id, skill_id) → LearningState
- update_learning_state(state, assessment_result) → LearningState
- get_session_state(session_id) → SessionState
- update_session_state(session_id, delta) → SessionState
- commit_mastery_decision(decision) → void
- get_competency_matrix(employee_id) → CompetencyMatrix

Storage:
- Session state → Redis (TTL: 24 hours)
- Learning state (persistent) → PostgreSQL
- Mastery history → PostgreSQL (immutable append-only log)
- Competency matrix cache → Redis (TTL: 5 minutes)

Concurrency:
- PostgreSQL row-level locking for mastery commits
- Redis SETNX for session state updates (prevent race conditions)
"""
import json
import structlog
from typing import Optional
from datetime import datetime
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

from app.models.learning_state import EmployeeLearningState
from app.models.assessment import MasteryHistory, AssessmentResult
from app.models.competency import Competency, Skill
from app.models.session import LearningSession

logger = structlog.get_logger()

# Redis TTL constants (from §5.2)
SESSION_STATE_TTL = 86400       # 24 hours
EMPLOYEE_CONTEXT_TTL = 3600     # 1 hour
COMPETENCY_GRAPH_TTL = 600      # 10 minutes
MASTERY_CACHE_TTL = 300         # 5 minutes
AGENT_LOCK_TTL = 30             # 30 seconds
RATE_SESSION_TTL = 86400        # 24 hours
CONTENT_REVIEWED_TTL = 14400    # 4 hours


class LearningStateManagerAgent:
    """Centralized state operations for the platform.
    No LLM — pure deterministic data operations.
    """

    def __init__(self, db_session: AsyncSession, redis: Redis):
        self.db = db_session
        self.redis = redis
        self.logger = logger.bind(agent="LearningStateManagerAgent")

    # --- LEARNING STATE (PostgreSQL) ---

    async def get_learning_state(
        self, employee_id: str, skill_id: str
    ) -> Optional[dict]:
        """Get persistent learning state for employee+skill."""
        result = await self.db.exec(
            select(EmployeeLearningState)
            .where(EmployeeLearningState.employee_id == employee_id)
            .where(EmployeeLearningState.skill_id == skill_id)
        )
        state = result.first()
        if not state:
            return None
        return {
            "employee_id": str(state.employee_id),
            "skill_id": str(state.skill_id),
            "competency_id": str(state.competency_id),
            "current_score": state.current_score,
            "mastery_level": state.mastery_level,
            "mastery_confidence": state.mastery_confidence,
            "knowledge_gaps": state.knowledge_gaps or [],
            "misconception_map": state.misconception_map or [],
            "learning_velocity": state.learning_velocity,
            "engagement_score": state.engagement_score,
            "total_interactions": state.total_interactions,
            "sessions_count": state.sessions_count,
            "last_assessed_at": state.last_assessed_at.isoformat() if state.last_assessed_at else None,
        }

    async def update_learning_state(
        self, employee_id: str, skill_id: str,
        assessment_result: dict,
    ) -> dict:
        """Update learning state with new assessment result."""
        result = await self.db.exec(
            select(EmployeeLearningState)
            .where(EmployeeLearningState.employee_id == employee_id)
            .where(EmployeeLearningState.skill_id == skill_id)
        )
        state = result.first()
        if not state:
            raise ValueError(f"No learning state for {employee_id}/{skill_id}")

        # Update scores with exponential moving average
        alpha = 0.3  # Weight for new score
        new_score = assessment_result.get("composite_score", 0)
        state.current_score = (alpha * new_score) + ((1 - alpha) * state.current_score)
        state.total_interactions += 1
        state.last_assessed_at = datetime.utcnow()

        # Update knowledge gaps and misconceptions
        if assessment_result.get("misconceptions"):
            existing = state.misconception_map or []
            for m in assessment_result["misconceptions"]:
                found = False
                for em in existing:
                    if em.get("pattern") == m.get("pattern"):
                        em["persistence_count"] = em.get("persistence_count", 0) + 1
                        found = True
                if not found:
                    existing.append({"pattern": m.get("pattern", ""), "persistence_count": 1})
            state.misconception_map = existing

        # Calculate learning velocity (score improvement rate)
        state.learning_velocity = new_score - state.current_score

        state.updated_at = datetime.utcnow()
        self.db.add(state)
        await self.db.commit()
        await self.db.refresh(state)

        # Invalidate Redis cache
        await self.redis.delete(f"mastery:{employee_id}:{skill_id}")

        self.logger.info("learning_state_updated",
            employee_id=employee_id, skill_id=skill_id,
            new_score=state.current_score)

        return await self.get_learning_state(employee_id, skill_id)

    async def initialize_learning_state(
        self, employee_id: str, skill_id: str,
        competency_id: str, initial_score: float = 0.0,
    ) -> dict:
        """Create initial learning state for employee+skill."""
        state = EmployeeLearningState(
            employee_id=employee_id,
            skill_id=skill_id,
            competency_id=competency_id,
            current_score=initial_score,
        )
        self.db.add(state)
        await self.db.commit()
        await self.db.refresh(state)
        return await self.get_learning_state(employee_id, skill_id)

    # --- SESSION STATE (Redis) ---

    async def get_session_state(self, session_id: str) -> Optional[dict]:
        """Get session state from Redis.
        Key: session:{session_id}:state (TTL: 24h)
        """
        data = await self.redis.get(f"session:{session_id}:state")
        if data:
            return json.loads(data)
        return None

    async def update_session_state(
        self, session_id: str, delta: dict,
    ) -> dict:
        """Update session state in Redis using SETNX for race prevention."""
        key = f"session:{session_id}:state"
        lock_key = f"session:{session_id}:lock"

        # Acquire lock (SETNX pattern for concurrency)
        acquired = await self.redis.set(lock_key, "1", nx=True, ex=5)
        if not acquired:
            self.logger.warning("session_state_lock_contention", session_id=session_id)
            # Wait briefly and retry
            import asyncio
            await asyncio.sleep(0.1)
            acquired = await self.redis.set(lock_key, "1", nx=True, ex=5)

        try:
            current = await self.get_session_state(session_id)
            if current is None:
                current = {}
            current.update(delta)
            await self.redis.set(key, json.dumps(current, default=str), ex=SESSION_STATE_TTL)
            return current
        finally:
            await self.redis.delete(lock_key)

    async def create_session_state(self, session_id: str, initial_state: dict) -> dict:
        """Initialize session state in Redis."""
        key = f"session:{session_id}:state"
        await self.redis.set(key, json.dumps(initial_state, default=str), ex=SESSION_STATE_TTL)
        return initial_state

    # --- MASTERY DECISIONS (PostgreSQL append-only) ---

    async def commit_mastery_decision(self, decision: dict) -> dict:
        """Commit mastery decision to PostgreSQL.
        Uses row-level locking for concurrency safety.
        Mastery history is immutable append-only.
        """
        # Row-level lock on learning state
        result = await self.db.exec(
            select(EmployeeLearningState)
            .where(EmployeeLearningState.employee_id == decision["employee_id"])
            .where(EmployeeLearningState.skill_id == decision["skill_id"])
            .with_for_update()  # Row-level lock
        )
        state = result.first()
        if not state:
            raise ValueError("Learning state not found")

        old_level = state.mastery_level

        # Update mastery level
        state.mastery_level = decision["new_mastery_level"]
        state.mastery_confidence = decision.get("confidence", 0.0)
        state.updated_at = datetime.utcnow()
        self.db.add(state)

        # Append to mastery history (immutable)
        history = MasteryHistory(
            employee_id=decision["employee_id"],
            skill_id=decision["skill_id"],
            old_level=old_level,
            new_level=decision["new_mastery_level"],
            decision=decision["mastery_decision"],
            confidence=decision.get("confidence"),
            evidence_summary=decision.get("evidence_summary", ""),
            decided_by=decision.get("decided_by", "ai"),
            override_reason=decision.get("override_reason"),
            session_id=decision.get("session_id"),
        )
        self.db.add(history)
        await self.db.commit()

        # Invalidate caches
        emp_id = decision["employee_id"]
        skill_id = decision["skill_id"]
        await self.redis.delete(f"mastery:{emp_id}:{skill_id}")

        self.logger.info("mastery_committed",
            employee_id=emp_id, skill_id=skill_id,
            old=old_level, new=decision["new_mastery_level"],
            decision=decision["mastery_decision"])

        return decision

    # --- COMPETENCY MATRIX (Cached in Redis) ---

    async def get_competency_matrix(self, employee_id: str) -> list[dict]:
        """Get full competency matrix for employee.
        Cache in Redis with 5-minute TTL.
        """
        cache_key = f"competency_matrix:{employee_id}"
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Build from PostgreSQL
        result = await self.db.exec(
            select(EmployeeLearningState)
            .where(EmployeeLearningState.employee_id == employee_id)
        )
        states = result.all()

        # Group by competency
        matrix = {}
        for s in states:
            comp_id = str(s.competency_id)
            if comp_id not in matrix:
                comp = await self.db.get(Competency, s.competency_id)
                matrix[comp_id] = {
                    "competency_id": comp_id,
                    "competency_name": comp.name if comp else "Unknown",
                    "skills": [],
                }
            skill = await self.db.get(Skill, s.skill_id)
            matrix[comp_id]["skills"].append({
                "skill_id": str(s.skill_id),
                "skill_name": skill.name if skill else "Unknown",
                "mastery_level": s.mastery_level,
                "current_score": s.current_score,
                "last_assessed_at": s.last_assessed_at.isoformat() if s.last_assessed_at else None,
            })

        # Calculate overall progress
        result_list = []
        for comp in matrix.values():
            total = len(comp["skills"])
            mastered = sum(1 for s in comp["skills"] if s["mastery_level"] >= 3)
            comp["overall_progress_pct"] = (mastered / total * 100) if total > 0 else 0
            comp["employee_id"] = employee_id
            result_list.append(comp)

        # Cache
        await self.redis.set(cache_key, json.dumps(result_list, default=str), ex=MASTERY_CACHE_TTL)
        return result_list

    # --- EMPLOYEE CONTEXT (Redis) ---

    async def set_employee_context(self, employee_id: str, context: dict):
        """Cache employee context in Redis (1h TTL)."""
        key = f"employee:{employee_id}:context"
        await self.redis.set(key, json.dumps(context, default=str), ex=EMPLOYEE_CONTEXT_TTL)

    async def get_employee_context(self, employee_id: str) -> Optional[dict]:
        data = await self.redis.get(f"employee:{employee_id}:context")
        return json.loads(data) if data else None

    # --- AGENT LOCK (Redis) ---

    async def acquire_agent_lock(self, agent_id: str, session_id: str) -> bool:
        """Prevent double-invocation of an agent.
        Key: agent:{agent_id}:lock (TTL: 30s)
        """
        return await self.redis.set(
            f"agent:{agent_id}:lock", session_id,
            nx=True, ex=AGENT_LOCK_TTL,
        )

    async def release_agent_lock(self, agent_id: str):
        await self.redis.delete(f"agent:{agent_id}:lock")


# --- LangGraph Node Functions ---

async def load_state(state: dict) -> dict:
    """LangGraph node: Load employee learning state at session start."""
    # This will be injected with dependencies at graph build time
    return {"current_node": "load_state"}


async def update_state(state: dict) -> dict:
    """LangGraph node: Update state after assessment scoring."""
    return {"current_node": "update_state"}
```

---

### Redis Key Schema (from §5.2 — Complete Reference)

| Redis Key Pattern | Value Structure | TTL |
|---|---|---|
| `session:{session_id}:state` | JSON: full SessionState (messages, scores, module) | 24h |
| `employee:{employee_id}:context` | JSON: role, active competencies, preferences | 1h |
| `competency:{comp_id}:graph` | JSON: skill DAG snapshot | 10m |
| `mastery:{emp_id}:{skill_id}` | JSON: current mastery level + confidence | 5m |
| `agent:{agent_id}:lock` | String: session_id (prevents double-invocation) | 30s |
| `rate:{employee_id}:session` | Counter: sessions today | 24h |
| `content:{hash}:reviewed` | JSON: reviewed content (cache approved items) | 4h |

---

### Verification Criteria

1. **Initialize state**: Create learning state → row in PostgreSQL
2. **Get state**: Retrieve by employee_id + skill_id → correct values
3. **Update with assessment**: Score updates via exponential moving average
4. **Session state Redis**: Create → get → update → get → values correct
5. **Mastery commit**: Row-level lock → append to mastery_history → update learning_state
6. **Matrix cache**: First call hits DB, second call (within 5min) hits Redis
7. **Agent lock**: SETNX prevents concurrent agent invocation
8. **Concurrency**: Two simultaneous mastery commits → one succeeds, one waits for lock

### Notes & Gotchas

- **No LLM**: This agent is pure deterministic data operations
- **Row-level locking**: `with_for_update()` in SQLAlchemy for PostgreSQL SELECT FOR UPDATE
- **Redis SETNX**: `set(key, value, nx=True)` for atomic lock acquisition
- **Exponential moving average**: `alpha=0.3` weights new scores; adjust based on learning velocity
- **Append-only mastery history**: Never update or delete mastery_history rows — they're an audit log
- **Cache invalidation**: Always delete Redis cache keys after PostgreSQL writes
