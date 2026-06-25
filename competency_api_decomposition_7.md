# Competency API & Decomposition Workflow

## Plan 7 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement all competency CRUD endpoints, the async AI decomposition workflow (as a LangGraph graph), the manager validation endpoint, and the full skill DAG management API. This wires Plan 6's Competency Architect Agent to the REST API and builds the `competency_decomposition_graph` LangGraph workflow.

### Prerequisites

- **Plan 3** (Auth & Security) — RBAC dependencies, error handling
- **Plan 4** (Neo4j Knowledge Graph) — Skill graph CRUD service
- **Plan 6** (Competency Architect Agent) — Agent implementation

### Spec References

| Section | Content |
|---------|---------|
| §8.3 Competency Routes | All 12 competency endpoints |
| §21.1 Flow 1: Competency Creation and Decomposition | Full API flow sequence |
| §9.1 FastAPI Router Structure | Router registration pattern (Listing 11) |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── api/v1/
│   └── competencies.py        # All competency routes
├── graphs/
│   └── competency_decomp.py   # LangGraph decomposition workflow (replace stub)
└── main.py                    # Register competencies router
```

---

### Detailed Implementation Steps

#### Step 1: Competency Routes

```python
# app/api/v1/competencies.py
"""Competency CRUD + AI Decomposition + Manager Validation endpoints.

From spec §8.3 — All Competency Routes:
- GET    /competencies                           List all for tenant
- POST   /competencies                           Create (manager only)
- GET    /competencies/{id}                      Detail
- PUT    /competencies/{id}                      Update metadata
- DELETE /competencies/{id}                      Soft delete (deprecated)
- POST   /competencies/{id}/decompose            Trigger AI decomposition (async)
- GET    /competencies/{id}/decompose/{job_id}   Poll decomposition result
- POST   /competencies/{id}/validate             Manager validates skill graph
- GET    /competencies/{id}/skills               Full skill DAG
- POST   /competencies/{id}/skills               Add skill node manually
- PUT    /competencies/{id}/skills/{skill_id}    Update skill
- DELETE /competencies/{id}/skills/{skill_id}    Remove skill
- POST   /competencies/{id}/skills/edges         Add prerequisite edge
- DELETE /competencies/{id}/skills/edges         Remove prerequisite edge
- GET    /competencies/{id}/versions             Version history
"""
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.db import get_async_session
from app.core.errors import PlatformError, ErrorCodes
from app.api.dependencies import require_role, get_current_user
from app.models.user import User
from app.models.competency import Competency, Skill, SkillEdge
from app.schemas.competency import (
    CompetencyCreate, CompetencyOut, CompetencyDecomposeRequest,
    CompetencyDecomposeResponse, CompetencyValidateRequest,
    SkillNodeCreate, SkillEdgeCreate,
)
from app.services.skill_graph import SkillGraphService
from app.agents.orchestrator import orchestrator

router = APIRouter()

# In-memory job store (replace with Redis in production)
_decomposition_jobs: dict[str, dict] = {}


@router.get("", response_model=list[CompetencyOut])
async def list_competencies(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """List all competencies for tenant."""
    result = await session.exec(
        select(Competency)
        .where(Competency.tenant_id == user.tenant_id)
        .order_by(Competency.created_at.desc())
    )
    return result.all()


@router.post("", response_model=CompetencyOut, status_code=201)
async def create_competency(
    data: CompetencyCreate,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    """Create new competency (manager only)."""
    comp = Competency(
        tenant_id=manager.tenant_id,
        name=data.name,
        description=data.description,
        business_relevance=data.business_relevance,
        target_roles=data.target_roles,
        created_by=manager.id,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@router.get("/{competency_id}", response_model=CompetencyOut)
async def get_competency(
    competency_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    comp = await session.get(Competency, competency_id)
    if not comp:
        raise PlatformError(ErrorCodes.COMPETENCY_NOT_FOUND,
            "Competency not found", str(competency_id), 404)
    return comp


@router.put("/{competency_id}", response_model=CompetencyOut)
async def update_competency(
    competency_id: uuid.UUID,
    data: CompetencyCreate,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    comp = await session.get(Competency, competency_id)
    if not comp:
        raise PlatformError(ErrorCodes.COMPETENCY_NOT_FOUND,
            "Competency not found", str(competency_id), 404)
    comp.name = data.name
    comp.description = data.description
    comp.business_relevance = data.business_relevance
    comp.target_roles = data.target_roles
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@router.delete("/{competency_id}")
async def delete_competency(
    competency_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    """Soft delete — sets status=deprecated."""
    comp = await session.get(Competency, competency_id)
    if not comp:
        raise PlatformError(ErrorCodes.COMPETENCY_NOT_FOUND,
            "Competency not found", str(competency_id), 404)
    comp.status = "deprecated"
    session.add(comp)
    await session.commit()
    return {"status": "deprecated", "competency_id": str(competency_id)}


@router.post("/{competency_id}/decompose", status_code=202)
async def trigger_decomposition(
    competency_id: uuid.UUID,
    data: CompetencyDecomposeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    """Trigger AI skill decomposition (async, returns job_id).
    
    From §21.1 Flow 1:
    POST /competencies/{id}/decompose — triggers async LangGraph workflow;
    returns job_id (202 Accepted)
    """
    comp = await session.get(Competency, competency_id)
    if not comp:
        raise PlatformError(ErrorCodes.COMPETENCY_NOT_FOUND,
            "Competency not found", str(competency_id), 404)

    # Check if decomposition already running
    for job in _decomposition_jobs.values():
        if (job.get("competency_id") == str(competency_id) and
                job.get("status") == "running"):
            raise PlatformError(ErrorCodes.DECOMPOSITION_IN_PROGRESS,
                "Decomposition already in progress", "", 409)

    job_id = str(uuid.uuid4())
    _decomposition_jobs[job_id] = {
        "competency_id": str(competency_id),
        "status": "running",
        "result": None,
    }

    # Run decomposition in background
    background_tasks.add_task(
        _run_decomposition, job_id, comp, data, session
    )

    return {"job_id": job_id, "status": "running"}


async def _run_decomposition(job_id, comp, data, session):
    """Background task: run the decomposition LangGraph workflow."""
    try:
        initial_state = {
            "session_id": job_id,
            "employee_id": "",
            "competency_id": str(comp.id),
            "workflow_type": "decomposition",
            "current_node": "start",
            "next_action": "",
            "messages": [],
            "current_proficiency": 0.0,
            "interaction_count": 0,
            "session_scores": [],
            "generated_content": {
                "name": comp.name,
                "description": comp.description,
                "target_roles": comp.target_roles or [],
                "industry_context": data.industry_context or "general",
                "max_depth": data.max_depth,
            },
            "assessment_result": None,
            "mastery_decision": None,
            "skill_graph": None,
            "error": None,
            "retry_count": 0,
            "fallback_triggered": False,
        }

        result = await orchestrator.run_workflow(
            "decomposition", initial_state, f"decomp-{comp.id}"
        )

        if result.get("error"):
            _decomposition_jobs[job_id]["status"] = "failed"
            _decomposition_jobs[job_id]["error"] = result["error"]
        else:
            _decomposition_jobs[job_id]["status"] = "completed"
            _decomposition_jobs[job_id]["result"] = result.get("skill_graph")

            # Update competency confidence
            comp.decomp_confidence = result["skill_graph"].get("confidence_score")
            comp.status = "under_review"

    except Exception as e:
        _decomposition_jobs[job_id]["status"] = "failed"
        _decomposition_jobs[job_id]["error"] = str(e)


@router.get("/{competency_id}/decompose/{job_id}")
async def poll_decomposition(
    competency_id: uuid.UUID,
    job_id: str,
    user: User = Depends(get_current_user),
):
    """Poll decomposition result. Frontend polls every 3s."""
    job = _decomposition_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{competency_id}/validate")
async def validate_competency(
    competency_id: uuid.UUID,
    data: CompetencyValidateRequest,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    """Manager validates/approves skill graph.
    
    From §21.1: Locks version, writes to PostgreSQL and Neo4j.
    """
    comp = await session.get(Competency, competency_id)
    if not comp:
        raise PlatformError(ErrorCodes.COMPETENCY_NOT_FOUND,
            "Competency not found", str(competency_id), 404)

    # Remove rejected nodes from DB and Neo4j
    for node_id in data.removed_nodes:
        skill = await session.get(Skill, node_id)
        if skill:
            await session.delete(skill)
            await SkillGraphService.remove_skill_node(str(node_id))

    # Update competency status
    comp.status = "active"
    comp.approved_by = manager.id
    from datetime import datetime
    comp.approved_at = datetime.utcnow()
    comp.version_minor += 1
    session.add(comp)
    await session.commit()

    return {"status": "validated", "competency_id": str(competency_id)}


@router.get("/{competency_id}/skills")
async def get_skill_dag(
    competency_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Get full skill DAG (nodes + edges) from Neo4j."""
    return await SkillGraphService.get_skill_graph(str(competency_id))


@router.post("/{competency_id}/skills", status_code=201)
async def add_skill(
    competency_id: uuid.UUID,
    data: SkillNodeCreate,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    """Manually add a skill node."""
    skill = Skill(
        competency_id=competency_id,
        name=data.name,
        description=data.description,
        hierarchy_level=data.hierarchy_level,
        difficulty_level=data.difficulty_level,
        learning_strategy=data.learning_strategy.value,
        estimated_minutes=data.estimated_minutes,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)

    # Also add to Neo4j
    await SkillGraphService.add_skill_node(
        str(competency_id), str(skill.id), skill.name,
        skill.description or "", skill.hierarchy_level,
        skill.difficulty_level, skill.learning_strategy or "conceptual",
    )
    return skill


@router.post("/{competency_id}/skills/edges")
async def add_edge(
    competency_id: uuid.UUID,
    data: SkillEdgeCreate,
    session: AsyncSession = Depends(get_async_session),
    manager: User = Depends(require_role("manager", "admin")),
):
    """Add prerequisite edge. Check for cycles before adding."""
    # Add to PostgreSQL
    edge = SkillEdge(
        prerequisite_id=uuid.UUID(data.prerequisite_name),  # Accept UUID string
        dependent_id=uuid.UUID(data.dependent_name),
        strength=data.strength,
    )
    session.add(edge)

    # Add to Neo4j
    await SkillGraphService.add_prerequisite_edge(
        data.prerequisite_name, data.dependent_name, data.strength,
    )

    # Check for cycles
    has_cycle = await SkillGraphService.check_cycle(str(competency_id))
    if has_cycle:
        # Rollback
        await session.rollback()
        await SkillGraphService.remove_prerequisite_edge(
            data.prerequisite_name, data.dependent_name,
        )
        raise PlatformError(ErrorCodes.CYCLE_DETECTED_IN_GRAPH,
            "Adding this edge would create a cycle", "", 422)

    await session.commit()
    return {"status": "edge_added"}
```

#### Step 2: LangGraph Decomposition Workflow

```python
# app/graphs/competency_decomp.py
"""Competency decomposition LangGraph workflow.

From spec §3 (Orchestrator):
competency_decomposition_graph:
Manager creates competency → Architect → Neo4j → Manager validation
"""
from langgraph.graph import StateGraph, END
from app.graphs.state import AgentState
from app.agents.competency_architect import competency_architect_node
from app.services.skill_graph import SkillGraphService
from app.graphs.error_handler import handle_error


async def save_to_neo4j(state: AgentState) -> dict:
    """Save decomposed skills to Neo4j after architect completes."""
    skill_graph = state.get("skill_graph", {})
    if not skill_graph:
        return {"error": "No skill graph to save"}

    await SkillGraphService.create_competency_subgraph(
        competency_id=skill_graph["competency_id"],
        competency_name=state.get("generated_content", {}).get("name", ""),
        version="1.0",
        status="under_review",
        tenant_id="",  # Set from context
        skill_nodes=skill_graph["skill_nodes"],
        skill_edges=skill_graph["skill_edges"],
    )
    return {"current_node": "save_to_neo4j", "next_action": "complete"}


def route_after_architect(state: AgentState) -> str:
    if state.get("error"):
        return "error"
    return "save"


def build_competency_decomp_graph(checkpointer):
    graph = StateGraph(AgentState)

    graph.add_node("architect", competency_architect_node)
    graph.add_node("save_to_neo4j", save_to_neo4j)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("architect")
    graph.add_conditional_edges("architect", route_after_architect, {
        "save": "save_to_neo4j",
        "error": "handle_error",
    })
    graph.add_edge("save_to_neo4j", END)
    graph.add_edge("handle_error", END)

    return graph.compile(checkpointer=checkpointer)
```

---

### Verification Criteria

1. **POST /competencies** → creates competency in DB, returns CompetencyOut
2. **POST /competencies/{id}/decompose** → returns 202 with job_id
3. **GET /competencies/{id}/decompose/{job_id}** → returns running/completed/failed
4. **On completed**: result includes skill_nodes, skill_edges, rationale, confidence_score
5. **POST /competencies/{id}/validate** → sets status=active, approved_by, approved_at
6. **GET /competencies/{id}/skills** → returns Neo4j skill DAG
7. **Cycle detection**: Adding a cyclic edge returns 422 CYCLE_DETECTED_IN_GRAPH
8. **RBAC**: Only manager/admin can create, decompose, validate

### Notes & Gotchas

- **Job store**: In-memory `_decomposition_jobs` dict is MVP-only; use Redis in production
- **Background task**: `BackgroundTasks` is simpler than Celery for MVP; consider task queue for production
- **Dual write**: Skills saved to both PostgreSQL AND Neo4j — maintain consistency
- **Version bumping**: `version_minor += 1` on validation; `version_major` for breaking changes
