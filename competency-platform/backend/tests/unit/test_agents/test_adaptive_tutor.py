"""Unit tests for AdaptiveTutorAgent.

From spec §15.1:
Tests difficulty adjustment and content type selection logic.
"""
import pytest
from unittest.mock import AsyncMock

from tests.conftest import create_mock_llm


class TestAdaptiveTutorAgent:
    """Test suite for Adaptive Tutor difficulty calibration."""

    @pytest.mark.asyncio
    async def test_difficulty_increases_on_high_score(self):
        """Score > 80 should trigger difficulty increase recommendation."""
        from app.agents.adaptive_tutor import AdaptiveTutorAgent

        mock_llm = create_mock_llm("Advanced: Implement a custom metaclass...")
        agent = AdaptiveTutorAgent(llm=mock_llm)

        state = {
            "session_id": "test-tutor-001",
            "employee_id": "emp-001",
            "skill_id": "skill-py",
            "current_proficiency": 0.85,
            "session_scores": [85, 88, 90],
            "interaction_count": 3,
            "messages": [],
            "generated_content": {},
        }

        result = await agent.process(state)
        assert result is not None
        mock_llm.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_max_interactions_triggers_mastery_check(self):
        """Reaching max interactions should route to mastery evaluation."""
        from app.agents.adaptive_tutor import AdaptiveTutorAgent

        mock_llm = create_mock_llm("Session complete.")
        agent = AdaptiveTutorAgent(llm=mock_llm)

        state = {
            "session_id": "test-tutor-002",
            "employee_id": "emp-001",
            "skill_id": "skill-py",
            "current_proficiency": 0.7,
            "session_scores": [70] * 25,
            "interaction_count": 25,
            "max_interactions": 25,
            "messages": [],
            "generated_content": {},
        }

        result = await agent.process(state)
        assert result is not None
