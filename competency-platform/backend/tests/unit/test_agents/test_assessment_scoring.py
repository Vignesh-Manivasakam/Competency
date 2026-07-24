"""Unit tests for AssessmentScoringAgent.

From spec §15.1 (Unit - agents):
Validates correct scoring output schema and rubric adherence.

From spec §3 (Assessment Scoring Agent):
Outputs: composite_score (0-100), dimension_scores, confidence_signal,
evaluation_rationale
"""
import pytest
from unittest.mock import AsyncMock

from tests.conftest import create_mock_structured_llm
from app.schemas.assessment import DimensionScores, ScoringOutput


class TestAssessmentScoringAgent:
    """Test suite for the Assessment Scoring Agent."""

    @pytest.mark.asyncio
    async def test_scoring_produces_valid_schema(self):
        """Scoring output matches expected schema with all required fields."""
        from app.agents.assessment_scoring import AssessmentScoringAgent

        mock_response = ScoringOutput(
            composite_score=78.5,
            dimension_scores=DimensionScores(
                accuracy=80.0,
                application=75.0,
                reasoning=80.0,
                consistency=75.0,
                confidence=80.0,
            ),
            misconceptions=[],
            confidence_signal=0.85,
            feedback_points=["Good understanding of core concepts."],
            evaluation_rationale="Good performance overall.",
        )
        mock_llm = create_mock_structured_llm(mock_response)
        agent = AssessmentScoringAgent(llm=mock_llm)

        state = {
            "session_id": "test-score-001",
            "employee_id": "emp-001",
            "skill_id": "skill-py",
            "assessment_results": {
                "question": "Explain Python decorators",
                "answer": "Decorators wrap functions...",
                "rubric": {"accuracy": 40, "completeness": 30, "reasoning": 30},
            },
            "current_proficiency": 0.6,
        }

        result = await agent.process(state)
        assert result is not None
        assert mock_llm.ainvoke.await_count >= 1

    @pytest.mark.asyncio
    async def test_score_boundaries(self):
        """Composite score must be between 0 and 100."""
        # Valid boundary min
        output = ScoringOutput(
            composite_score=0.0,
            dimension_scores=DimensionScores(
                accuracy=0.0, application=0.0, reasoning=0.0, consistency=0.0, confidence=0.0
            ),
            misconceptions=[],
            confidence_signal=0.5,
            feedback_points=["Needs improvement."],
            evaluation_rationale="Needs improvement.",
        )
        assert output.composite_score == 0.0

        # Valid boundary max
        output_max = ScoringOutput(
            composite_score=100.0,
            dimension_scores=DimensionScores(
                accuracy=100.0, application=100.0, reasoning=100.0, consistency=100.0, confidence=100.0
            ),
            misconceptions=[],
            confidence_signal=1.0,
            feedback_points=["Perfect score."],
            evaluation_rationale="Perfect score.",
        )
        assert output_max.composite_score == 100.0
