"""Unit tests for MasteryEvaluationAgent.

From spec §15.1 (Unit - agents):
Tests decision rules: UPGRADE, MAINTAIN, DOWNGRADE logic.

From spec §3 (Mastery Evaluation Agent):
Decision Rules (hard-coded, LLM confirms):
  Score >= threshold for 3 consecutive sessions
  AND error rate < 12%
  AND confidence >= 0.80
  = upgrade candidate
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import create_mock_structured_llm


class TestMasteryEvaluationRules:
    """Test the hard-coded decision rules independently of LLM."""

    def test_upgrade_all_criteria_met(self):
        """3 consecutive scores above threshold + low error rate = UPGRADE."""
        from app.agents.mastery_evaluation import MasteryEvaluationAgent

        agent = MasteryEvaluationAgent(llm=AsyncMock())

        assessments = [
            {"composite_score": 70, "confidence_signal": 0.85, "interaction_count": 10},
            {"composite_score": 72, "confidence_signal": 0.90, "interaction_count": 10},
            {"composite_score": 75, "confidence_signal": 0.88, "interaction_count": 10},
        ]
        errors = []  # 0 errors → 0% error rate

        result = agent._apply_rules(assessments, current_level=2, errors=errors)
        assert result["decision"] == "UPGRADE"

    def test_maintain_insufficient_data(self):
        """Fewer than 3 sessions → MAINTAIN (insufficient data)."""
        from app.agents.mastery_evaluation import MasteryEvaluationAgent

        agent = MasteryEvaluationAgent(llm=AsyncMock())

        assessments = [
            {"composite_score": 90, "confidence_signal": 0.95, "interaction_count": 10},
        ]

        result = agent._apply_rules(assessments, current_level=1, errors=[])
        assert result["decision"] == "MAINTAIN"
        assert "Insufficient" in result["reason"]

    def test_maintain_low_confidence(self):
        """Scores above threshold but low confidence → MAINTAIN."""
        from app.agents.mastery_evaluation import MasteryEvaluationAgent

        agent = MasteryEvaluationAgent(llm=AsyncMock())

        assessments = [
            {"composite_score": 70, "confidence_signal": 0.50, "interaction_count": 10},
            {"composite_score": 72, "confidence_signal": 0.55, "interaction_count": 10},
            {"composite_score": 75, "confidence_signal": 0.60, "interaction_count": 10},
        ]

        result = agent._apply_rules(assessments, current_level=2, errors=[])
        assert result["decision"] == "MAINTAIN"

    def test_downgrade_consistent_underperformance(self):
        """3 consecutive very low scores → DOWNGRADE."""
        from app.agents.mastery_evaluation import MasteryEvaluationAgent

        agent = MasteryEvaluationAgent(llm=AsyncMock())

        assessments = [
            {"composite_score": 20, "confidence_signal": 0.3, "interaction_count": 10},
            {"composite_score": 18, "confidence_signal": 0.25, "interaction_count": 10},
            {"composite_score": 22, "confidence_signal": 0.28, "interaction_count": 10},
        ]

        result = agent._apply_rules(assessments, current_level=2, errors=[])
        assert result["decision"] == "DOWNGRADE"

    def test_maintain_high_error_rate(self):
        """Good scores but error rate > 12% → MAINTAIN."""
        from app.agents.mastery_evaluation import MasteryEvaluationAgent

        agent = MasteryEvaluationAgent(llm=AsyncMock())

        assessments = [
            {"composite_score": 70, "confidence_signal": 0.85, "interaction_count": 10},
            {"composite_score": 72, "confidence_signal": 0.90, "interaction_count": 10},
            {"composite_score": 75, "confidence_signal": 0.88, "interaction_count": 10},
        ]
        # 5 errors out of 30 interactions = 16.7% > 12%
        errors = ["err1", "err2", "err3", "err4", "err5"]

        result = agent._apply_rules(assessments, current_level=2, errors=errors)
        assert result["decision"] == "MAINTAIN"
