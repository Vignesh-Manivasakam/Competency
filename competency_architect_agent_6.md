# Competency Architect Agent

## Plan 6 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the Competency Architect Agent — the first and most critical agent. It takes a manager's competency definition and decomposes it into a structured, validated skill DAG using GPT-4o with structured output. Includes prompt engineering, Neo4j integration for deduplication, pgvector similarity search for existing competencies, and the complete decomposition pipeline with confidence scoring.

### Prerequisites

- **Plan 4** (Neo4j Knowledge Graph) — Skill graph CRUD operations
- **Plan 5** (LangGraph Orchestrator) — BaseAgent class, LLM Router, LangSmith tracing

### Spec References

| Section | Content |
|---------|---------|
| §3 Competency Architect Agent | Full agent spec: inputs, outputs, tools, prompt strategy, failure handling |
| §7 Pydantic Schemas | SkillNodeCreate, SkillEdgeCreate, CompetencyDecomposeRequest/Response, CompetencyValidateRequest |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── agents/
│   └── competency_architect.py   # Agent implementation
├── schemas/
│   └── competency.py             # Pydantic request/response models
└── prompts/
    └── competency_architect.txt  # System prompt template
```

---

### Detailed Implementation Steps

#### Step 1: Pydantic Schemas (from §7 Listing 9)

```python
# app/schemas/competency.py
from pydantic import BaseModel, Field, UUID4
from typing import Optional
from enum import Enum
from datetime import datetime


class SkillStrategy(str, Enum):
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    APPLIED = "applied"
    ANALYTICAL = "analytical"


class SkillNodeCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str
    hierarchy_level: int = Field(default=1, ge=1, le=3)
    difficulty_level: int = Field(default=1, ge=1, le=5)
    learning_strategy: SkillStrategy = SkillStrategy.CONCEPTUAL
    estimated_minutes: int = Field(default=60, ge=5, le=480)


class SkillEdgeCreate(BaseModel):
    prerequisite_name: str  # Name-based for LLM output; resolved to UUID later
    dependent_name: str
    strength: float = Field(default=1.0, ge=0.0, le=1.0)


class CompetencyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str
    business_relevance: Optional[str] = None
    target_roles: list[str] = Field(default_factory=list)


class CompetencyDecomposeRequest(BaseModel):
    competency_id: UUID4
    max_depth: int = Field(default=2, ge=1, le=3)
    industry_context: Optional[str] = None


class CompetencyDecomposeResponse(BaseModel):
    competency_id: UUID4
    skill_nodes: list[dict]
    skill_edges: list[dict]
    rationale: str
    confidence_score: float
    requires_manager_review: bool


class CompetencyValidateRequest(BaseModel):
    competency_id: UUID4
    approved_nodes: list[UUID4]
    removed_nodes: list[UUID4] = Field(default_factory=list)
    manager_notes: Optional[str] = None


class CompetencyOut(BaseModel):
    id: UUID4
    name: str
    description: Optional[str]
    status: str
    version_major: int
    version_minor: int
    target_roles: list[str]
    decomp_confidence: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Structured output schema for LLM ---
class DecompositionOutput(BaseModel):
    """Schema for GPT-4o structured output (JSON schema enforcement)."""
    skill_nodes: list[SkillNodeCreate]
    skill_edges: list[SkillEdgeCreate]
    decomposition_rationale: str = Field(
        ..., description="Explanation of why skills were decomposed this way"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence in the decomposition quality (0.0-1.0)"
    )
```

#### Step 2: System Prompt Template

```text
# prompts/competency_architect.txt
You are a Competency Architect Agent for an AI-powered learning platform.

Your role is to decompose a manager-defined competency into a structured,
validated skill DAG (Directed Acyclic Graph).

## Context
- Industry: {industry_context}
- Target Roles: {target_roles}
- Max Depth: {max_depth} levels of hierarchy

## Instructions
1. Analyze the competency name and description carefully
2. Decompose into concrete, measurable skills organized in a DAG
3. Each skill should be:
   - Specific enough to be assessed independently
   - Mapped to a hierarchy level (1=foundational, 2=intermediate, 3=advanced)
   - Assigned a difficulty level (1-5)
   - Classified with a learning strategy (conceptual/procedural/applied/analytical)
   - Given a realistic time estimate in minutes
4. Define prerequisite relationships between skills
5. Ensure the graph is a valid DAG (no cycles)
6. Use O*NET taxonomy hints where applicable for standardization
7. Consider industry-specific requirements for {industry_context}

## Existing Skills in System
{existing_skills}

## Similar Competencies Found
{similar_competencies}

If any existing skills match closely, reference them instead of creating duplicates.

## Output Requirements
- Return a structured JSON with skill_nodes, skill_edges, decomposition_rationale, and confidence_score
- Each skill must have: name, description, hierarchy_level, difficulty_level, learning_strategy, estimated_minutes
- Each edge must have: prerequisite_name, dependent_name, strength
- Confidence score: Set below 0.70 if you are uncertain about the decomposition
- Keep total skills between 4-15 for max_depth=2, 8-25 for max_depth=3
```

#### Step 3: Agent Implementation

```python
# app/agents/competency_architect.py
"""Competency Architect Agent — decomposes competencies into skill DAGs.

From spec §3:
Role: Decomposes a manager-defined competency into a structured,
validated skill DAG.

Covers (Full Spec): Competency Analysis + Architect + Taxonomy +
Industry Intelligence + Governance Validation (5 agents merged)

LangGraph Node: competency_architect_node
"""
import uuid
import structlog
from typing import Optional
from pathlib import Path

from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.schemas.competency import DecompositionOutput, SkillNodeCreate
from app.services.llm_router import get_llm_structured
from app.services.langsmith import get_runnable_config
from app.services.skill_graph import SkillGraphService
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "competency_architect.txt"


class CompetencyArchitectAgent(BaseAgent):
    """Decomposes competencies into structured skill DAGs.
    
    Inputs: competency_name, competency_description, target_roles,
            industry_context, max_depth
    Outputs: skill_nodes, skill_edges, decomposition_rationale,
             confidence_score
    Tools: Neo4j graph query, pgvector similarity search
    LLM: GPT-4o (structured output mode, JSON schema enforcement)
    """

    def __init__(self, llm=None):
        super().__init__(agent_name="CompetencyArchitectAgent")
        self.structured_llm = llm or get_llm_structured(
            self.agent_name, DecompositionOutput
        )

    async def process(self, state: AgentState) -> dict:
        """Execute competency decomposition."""
        competency_id = state.get("competency_id", "")
        session_id = state.get("session_id", "")

        # Extract inputs from state
        competency_data = state.get("generated_content", {})
        competency_name = competency_data.get("name", "")
        description = competency_data.get("description", "")
        target_roles = competency_data.get("target_roles", [])
        industry_context = competency_data.get("industry_context", "general")
        max_depth = competency_data.get("max_depth", 2)

        # Tool 1: Check existing skills in Neo4j for deduplication
        existing_skills = await SkillGraphService.find_similar_skills(
            competency_name, limit=10
        )

        # Tool 2: pgvector similarity search for similar competencies
        # (Implemented in Plan 10 with RAG pipeline; placeholder for now)
        similar_competencies = []

        # Build prompt
        system_prompt = self._build_prompt(
            industry_context=industry_context,
            target_roles=target_roles,
            max_depth=max_depth,
            existing_skills=existing_skills,
            similar_competencies=similar_competencies,
        )

        user_prompt = (
            f"Competency: {competency_name}\n\n"
            f"Description: {description}\n\n"
            f"Please decompose this competency into a structured skill DAG."
        )

        # Invoke LLM with structured output
        config = self.get_config(session_id)
        result: DecompositionOutput = await self.structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            config=config,
        )

        # Process result
        requires_review = result.confidence_score < 0.70

        # Assign UUIDs to skill nodes
        skill_nodes_with_ids = []
        name_to_id = {}
        for node in result.skill_nodes:
            node_id = str(uuid.uuid4())
            name_to_id[node.name] = node_id
            skill_nodes_with_ids.append({
                "id": node_id,
                "name": node.name,
                "description": node.description,
                "hierarchy_level": node.hierarchy_level,
                "difficulty_level": node.difficulty_level,
                "learning_strategy": node.learning_strategy.value,
                "estimated_minutes": node.estimated_minutes,
            })

        # Resolve edge names to UUIDs
        skill_edges_with_ids = []
        for edge in result.skill_edges:
            prereq_id = name_to_id.get(edge.prerequisite_name)
            dep_id = name_to_id.get(edge.dependent_name)
            if prereq_id and dep_id:
                skill_edges_with_ids.append({
                    "prerequisite_id": prereq_id,
                    "dependent_id": dep_id,
                    "strength": edge.strength,
                })

        logger.info(
            "decomposition_complete",
            competency_id=competency_id,
            skills_count=len(skill_nodes_with_ids),
            edges_count=len(skill_edges_with_ids),
            confidence=result.confidence_score,
            requires_review=requires_review,
        )

        return {
            "skill_graph": {
                "competency_id": competency_id,
                "skill_nodes": skill_nodes_with_ids,
                "skill_edges": skill_edges_with_ids,
                "rationale": result.decomposition_rationale,
                "confidence_score": result.confidence_score,
                "requires_manager_review": requires_review,
            },
            "next_action": "review" if requires_review else "complete",
        }

    def _build_prompt(
        self,
        industry_context: str,
        target_roles: list[str],
        max_depth: int,
        existing_skills: list[dict],
        similar_competencies: list[dict],
    ) -> str:
        """Build the system prompt from template."""
        template = PROMPT_TEMPLATE.read_text()
        return template.format(
            industry_context=industry_context,
            target_roles=", ".join(target_roles) or "General",
            max_depth=max_depth,
            existing_skills=self._format_existing_skills(existing_skills),
            similar_competencies=self._format_similar(similar_competencies),
        )

    @staticmethod
    def _format_existing_skills(skills: list[dict]) -> str:
        if not skills:
            return "No existing skills found in the system."
        lines = ["Existing skills in the system:"]
        for s in skills:
            lines.append(f"  - {s.get('name', 'Unknown')} (Level {s.get('level', '?')})")
        return "\n".join(lines)

    @staticmethod
    def _format_similar(comps: list[dict]) -> str:
        if not comps:
            return "No similar competencies found."
        lines = ["Similar competencies:"]
        for c in comps:
            lines.append(f"  - {c.get('name', 'Unknown')}: {c.get('description', '')[:100]}")
        return "\n".join(lines)


# LangGraph node function
competency_architect = CompetencyArchitectAgent()


async def competency_architect_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Competency Architect Agent."""
    return await competency_architect(state)
```

---

### Failure Handling (from §3)

- **Confidence < 0.70**: Return partial result with `requires_manager_review: true` flag. Manager can manually edit in DAG editor.
- **LLM failure**: Retry with broader context (max 2 retries) — handled by `BaseAgent.__call__()` exponential backoff.
- **Neo4j unavailable**: Proceed without deduplication check (log warning).

---

### Verification Criteria

1. **Unit test with mock LLM**: Create mock returning valid DecompositionOutput → agent produces correct skill_nodes and skill_edges with UUIDs
2. **Low confidence handling**: Mock LLM returning confidence=0.50 → `requires_manager_review=True`
3. **Structured output**: LLM called with `with_structured_output(DecompositionOutput)` enforces JSON schema
4. **Name-to-UUID resolution**: Edges correctly map prerequisite/dependent names to generated UUIDs
5. **Neo4j deduplication**: Agent calls `find_similar_skills()` before decomposition
6. **LangSmith trace**: After invocation, trace appears in LangSmith with `CompetencyArchitectAgent` tag
7. **Prompt includes context**: System prompt contains industry_context, target_roles, existing skills

### Notes & Gotchas

- **Structured output**: Use `method="json_schema"` for maximum reliability with GPT-4o
- **Edge resolution**: LLM outputs skill names in edges (not UUIDs) — agent resolves names to UUIDs post-generation
- **Cycle prevention**: DAG validity should be checked after generation (client-side topological sort in frontend, server-side in Neo4j)
- **Token limits**: For max_depth=3, skill counts can reach 25 — ensure prompt + response fits in context window
- **Temperature**: Use 0.1 for structured output to maximize schema compliance
