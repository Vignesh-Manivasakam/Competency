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
    """Trigger AI skill decomposition (async, returns job_id)."""
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
        _run_decomposition_task, job_id, competency_id, data
    )

    return {"job_id": job_id, "status": "running"}


async def _run_decomposition_task(job_id: str, competency_id: uuid.UUID, data: CompetencyDecomposeRequest):
    """Background task: run the decomposition LangGraph workflow."""
    # We open a new session for the background task to avoid sharing session across threads
    from app.core.db import async_session_factory
    try:
        async with async_session_factory() as session:
            comp = await session.get(Competency, competency_id)
            if not comp:
                _decomposition_jobs[job_id]["status"] = "failed"
                _decomposition_jobs[job_id]["error"] = "Competency deleted"
                return

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

                # Update competency confidence & status
                comp.decomp_confidence = result["skill_graph"].get("confidence_score")
                comp.status = "under_review"
                session.add(comp)
                await session.commit()

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
    
    Locks version, writes to PostgreSQL and Neo4j.
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
