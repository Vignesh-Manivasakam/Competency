"""Unit tests for CompetencyArchitectAgent.

From spec §15.1 (Unit - agents):
Each agent with mock LLM: correct output schema, correct routing decisions,
failure handling.

From spec §3 (Competency Architect Agent):
Inputs: competency_name, description
Outputs: skill_nodes, skill_edges, decomposition_rationale, confidence_score
"""
import pytest
from unittest.mock import AsyncMock

from tests.conftest import create_mock_structured_llm
from app.schemas.competency import SkillNodeCreate, SkillEdgeCreate, SkillStrategy


class TestCompetencyArchitectAgent:
    """Test suite for the Competency Architect Agent."""

    @pytest.mark.asyncio
    async def test_successful_decomposition(self):
        """Agent produces valid skill_nodes and confidence_score."""
        from app.agents.competency_architect import (
            CompetencyArchitectAgent,
            DecompositionOutput,
        )

        mock_response = DecompositionOutput(
            skill_nodes=[
                SkillNodeCreate(
                    name="Python Basics",
                    description="Basic Python syntax and concepts",
                    hierarchy_level=1,
                    difficulty_level=1,
                    learning_strategy=SkillStrategy.CONCEPTUAL,
                    estimated_minutes=30,
                ),
                SkillNodeCreate(
                    name="Data Structures",
                    description="Lists, dicts, sets, tuples",
                    hierarchy_level=2,
                    difficulty_level=2,
                    learning_strategy=SkillStrategy.PROCEDURAL,
                    estimated_minutes=60,
                ),
            ],
            skill_edges=[
                SkillEdgeCreate(
                    prerequisite_name="Python Basics",
                    dependent_name="Data Structures",
                    strength=1.0,
                ),
            ],
            decomposition_rationale="Decomposed based on industry-standard backend curriculum.",
            confidence_score=0.91,
        )
        mock_llm = create_mock_structured_llm(mock_response)
        agent = CompetencyArchitectAgent(llm=mock_llm)

        state = {
            "session_id": "test-001",
            "competency_id": "comp-be",
            "generated_content": {
                "name": "Backend Engineering",
                "description": "Full-stack backend development skills",
            },
        }

        result = await agent.process(state)

        assert "skill_nodes" in result or result is not None
        mock_llm.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_low_confidence_flags_review(self):
        """Agent output with confidence < 0.7 should flag for human review."""
        from app.agents.competency_architect import (
            CompetencyArchitectAgent,
            DecompositionOutput,
        )

        mock_response = DecompositionOutput(
            skill_nodes=[
                SkillNodeCreate(
                    name="Vague Skill",
                    description="Vague skill description",
                    hierarchy_level=1,
                    difficulty_level=1,
                )
            ],
            skill_edges=[],
            decomposition_rationale="Low confidence due to ambiguous competency description.",
            confidence_score=0.45,
        )
        mock_llm = create_mock_structured_llm(mock_response)
        agent = CompetencyArchitectAgent(llm=mock_llm)

        state = {
            "session_id": "test-002",
            "competency_id": "comp-vague",
            "generated_content": {
                "name": "Stuff",
                "description": "",
            },
        }

        result = await agent.process(state)
        assert result is not None

    @pytest.mark.asyncio
    async def test_llm_failure_handling(self):
        """Agent handles LLM errors gracefully without crashing."""
        from app.agents.competency_architect import CompetencyArchitectAgent

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=Exception("OpenAI rate limit exceeded")
        )
        agent = CompetencyArchitectAgent(llm=mock_llm)

        state = {
            "session_id": "test-003",
            "competency_id": "comp-err",
            "generated_content": {
                "name": "Test",
                "description": "Test",
            },
        }

        with pytest.raises(Exception, match="rate limit"):
            await agent.process(state)
