"""Integration tests for the learning session LangGraph workflow.

From spec §15.1 (Integration - workflows):
Full LangGraph graph: session loop, mastery decision — with mock LLM.

From §4.2 (Listing 2):
Session graph: generate_content → present_and_wait → score_response →
decide_next → (loop or check_mastery)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestLearningSessionWorkflow:
    """Test the learning session graph loop."""

    @pytest.mark.asyncio
    async def test_session_graph_builds(self, sample_agent_state):
        """Session graph compiles without errors."""
        from app.graphs.learning_session import build_learning_session_graph

        mock_checkpointer = MagicMock()
        graph = build_learning_session_graph(mock_checkpointer)
        assert graph is not None

    @pytest.mark.asyncio
    async def test_session_loop_terminates(self, sample_agent_state):
        """Session exits loop when max_interactions reached.

        From §4.2: route_after_score routes to check_mastery when
        interaction_count >= max_interactions.
        """
        state = sample_agent_state.copy()
        state["interaction_count"] = 25
        state["max_interactions"] = 25

        from app.graphs.learning_session import route_after_score

        result = route_after_score(state)
        assert result in ("check_mastery", "session_end")

    @pytest.mark.asyncio
    async def test_session_continues_on_low_interaction_count(self, sample_agent_state):
        """Session loops back to generate_content when under max interactions."""
        state = sample_agent_state.copy()
        state["interaction_count"] = 3
        state["max_interactions"] = 25
        state["next_action"] = "continue"

        from app.graphs.learning_session import route_after_score

        result = route_after_score(state)
        assert result in ("generate_content", "continue")
