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
        try:
            existing_skills = await SkillGraphService.find_similar_skills(
                competency_name, limit=10
            )
        except Exception as e:
            logger.warning("neo4j_error_deduplication_failed", error=str(e))
            existing_skills = []

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
