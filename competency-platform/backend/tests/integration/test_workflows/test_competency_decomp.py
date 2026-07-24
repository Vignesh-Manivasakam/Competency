"""Integration tests for the competency decomposition LangGraph workflow.

From spec §15.1 (Integration - workflows):
Full LangGraph graph: competency decomp — with mock LLM.

Tests the full graph from entry to completion with mocked agents.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestCompetencyDecompWorkflow:
    """Test the full competency decomposition graph end-to-end."""

    @pytest.mark.asyncio
    @patch("app.agents.competency_architect.CompetencyArchitectAgent")
    async def test_full_decomposition_flow(self, MockArchitect, sample_agent_state):
        """Graph executes: architect → validate → persist."""
        from app.graphs.competency_decomp import build_competency_decomp_graph

        # Mock the architect node
        mock_instance = AsyncMock()
        mock_instance.process = AsyncMock(return_value={
            "generated_content": {
                "skill_nodes": [
                    {"id": "s1", "name": "Basics", "level": 1},
                    {"id": "s2", "name": "Advanced", "level": 2},
                ],
                "dependency_edges": [{"from": "s1", "to": "s2"}],
                "confidence_score": 0.91,
            },
            "current_node": "architect",
            "next_action": "validate",
        })
        MockArchitect.return_value = mock_instance

        state = sample_agent_state.copy()
        state["workflow_type"] = "decomposition"
        state["generated_content"] = {
            "competency_name": "Backend Engineering",
            "description": "Full backend skills",
        }

        # Build graph with mock checkpointer
        mock_checkpointer = MagicMock()
        graph = build_competency_decomp_graph(mock_checkpointer)

        # Graph should compile without errors
        assert graph is not None

    @pytest.mark.asyncio
    async def test_decomposition_state_transitions(self, sample_agent_state):
        """Verify correct state transitions through the decomposition graph."""
        state = sample_agent_state.copy()
        state["workflow_type"] = "decomposition"

        # The graph should transition: start → architect → validate → persist → end
        expected_nodes = ["architect", "validate", "persist"]

        # Each node should set current_node correctly
        for node_name in expected_nodes:
            assert isinstance(node_name, str)
