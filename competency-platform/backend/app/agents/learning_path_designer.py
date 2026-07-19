# app/agents/learning_path_designer.py
"""Learning Path Designer Agent — personalized non-linear learning paths.

From spec §3:
Role: Constructs a personalised, non-linear learning path for a specific
employee and skill.

Inputs: employee_id, skill_id, learning_state, skill_graph (DAG from Neo4j),
        prerequisite_states
Outputs: learning_path (list[PathNode] with branching conditions),
         estimated_sessions, entry_point

Tools: Read learning state from Redis/PostgreSQL, Neo4j prerequisite traversal
Memory Scope: Short-term (employee state within session)
LLM: GPT-4o-mini (fast; path planning is rule-heavy, less creative)

Prompt Strategy: Chain-of-thought. Provides current state + skill graph +
prerequisite completion. Generates sequenced plan with branching logic
(if score > threshold, skip to advanced).

Failure Handling: Fallback to default sequential path from skill hierarchy.
"""
import structlog
from pydantic import BaseModel, Field
from typing import Optional
from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.services.llm_router import get_llm, get_llm_structured
from app.services.langsmith import get_runnable_config
from app.services.skill_graph import SkillGraphService
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()


class PathNode(BaseModel):
    skill_id: str
    skill_name: str
    content_type: str  # explanation, quiz, scenario, dialogue
    difficulty_level: int = Field(ge=1, le=5)
    estimated_minutes: int = 30
    branch_condition: Optional[str] = None  # e.g., "if score > 75, skip to advanced"
    is_optional: bool = False


class LearningPathOutput(BaseModel):
    learning_path: list[PathNode]
    estimated_sessions: int
    entry_point_index: int = 0
    path_rationale: str


SYSTEM_PROMPT = """You are a Learning Path Designer Agent for an AI-powered competency learning platform.

Your role is to construct a personalized, non-linear learning path for an employee.

## Employee Current State
- Current Score: {current_score}/100
- Mastery Level: {mastery_level}/5 ({mastery_name})
- Total Interactions: {total_interactions}
- Knowledge Gaps: {knowledge_gaps}
- Learning Velocity: {learning_velocity}

## Skill Graph (DAG)
{skill_graph}

## Prerequisite States
{prerequisite_states}

## Path Design Rules
1. Start from the employee's current level — don't repeat mastered content
2. Include branching conditions: "if score > X, skip to Y"
3. Mix content types for engagement: explanation → quiz → scenario → dialogue
4. Place prerequisites before dependent skills
5. Mark optional advanced content for fast learners
6. Estimate realistic session counts based on difficulty and velocity
7. If the employee has misconceptions, include targeted remediation nodes
8. Use chain-of-thought: think step by step about the optimal sequence

## Think Step-by-Step
1. What has the employee already mastered?
2. What are their weakest areas?
3. What's the optimal learning sequence considering prerequisites?
4. Where should branching happen?
5. What's the realistic session estimate?
"""


class LearningPathDesignerAgent(BaseAgent):
    """Constructs personalized non-linear learning paths."""

    def __init__(self, llm=None):
        super().__init__(agent_name="LearningPathDesignerAgent")
        self.structured_llm = llm or get_llm_structured(
            self.agent_name, LearningPathOutput
        )

    async def process(self, state: AgentState) -> dict:
        session_id = state.get("session_id", "")
        employee_id = state.get("employee_id", "")
        skill_id = state.get("skill_id", "")
        competency_id = state.get("competency_id", "")

        # Get skill graph from Neo4j
        skill_graph = await SkillGraphService.get_skill_graph(competency_id)
        topo_order = await SkillGraphService.get_topological_order(competency_id)

        # Get learning state (from state dict, set by load_state node)
        learning_state = state.get("generated_content", {}).get("learning_state", {})
        prerequisite_states = state.get("generated_content", {}).get("prerequisite_states", [])

        # Prevent index errors on mastery name list lookup
        mastery_lvl = learning_state.get("mastery_level", 0)
        mastery_names = ["Not Started", "Awareness", "Developing", "Proficient", "Advanced", "Mastered"]
        mastery_name = mastery_names[mastery_lvl] if 0 <= mastery_lvl < len(mastery_names) else "Unknown"

        system = SYSTEM_PROMPT.format(
            current_score=learning_state.get("current_score", 0),
            mastery_level=mastery_lvl,
            mastery_name=mastery_name,
            total_interactions=learning_state.get("total_interactions", 0),
            knowledge_gaps=learning_state.get("knowledge_gaps", []),
            learning_velocity=learning_state.get("learning_velocity", 0),
            skill_graph=str(skill_graph),
            prerequisite_states=str(prerequisite_states),
        )

        config = self.get_config(session_id)

        try:
            result: LearningPathOutput = await self.structured_llm.ainvoke(
                [SystemMessage(content=system),
                 HumanMessage(content=f"Design a learning path for skill {skill_id}")],
                config=config,
            )

            return {
                "generated_content": {
                    **state.get("generated_content", {}),
                    "learning_path": [p.model_dump() for p in result.learning_path],
                    "estimated_sessions": result.estimated_sessions,
                    "entry_point": result.entry_point_index,
                },
                "current_node": "design_path",
            }

        except Exception as e:
            # Fallback: sequential path from topological order
            logger.warning("path_design_fallback", error=str(e))
            fallback_path = self._generate_fallback_path(skill_graph, topo_order)
            return {
                "generated_content": {
                    **state.get("generated_content", {}),
                    "learning_path": fallback_path,
                    "estimated_sessions": len(fallback_path),
                    "entry_point": 0,
                },
                "current_node": "design_path",
                "fallback_triggered": True,
            }

    def _generate_fallback_path(self, skill_graph: dict, topo_order: list) -> list:
        """Default sequential path from skill hierarchy on LLM failure."""
        nodes = {n["id"]: n for n in skill_graph.get("nodes", [])}
        path = []
        for skill_id in topo_order:
            node = nodes.get(skill_id, {})
            path.append({
                "skill_id": skill_id,
                "skill_name": node.get("name", "Unknown"),
                "content_type": "explanation",
                "difficulty_level": node.get("difficulty", 1),
                "estimated_minutes": 30,
                "branch_condition": None,
                "is_optional": False,
            })
        return path


# LangGraph node
path_designer = LearningPathDesignerAgent()


async def design_path_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Learning Path Designer Agent."""
    return await path_designer(state)
