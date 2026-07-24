"""LangSmith evaluator harness for LLM output quality.

From spec §15.1 (LLM Eval layer):
Agent output quality: decomposition accuracy, assessment scoring accuracy
vs human labels — using LangSmith Evaluators.

These tests require:
- LANGCHAIN_API_KEY to be set
- A LangSmith dataset with human-labeled examples
- Run with: pytest tests/eval/ -m llm_eval --langsmith

Datasets required in LangSmith:
  1. "competency-decomposition-eval" — competency name → expected skill nodes
  2. "assessment-scoring-eval" — question/answer/rubric → expected score range
"""
import pytest
import json
from unittest.mock import AsyncMock

# Mark all tests in this module as llm_eval (skipped in regular CI)
pytestmark = pytest.mark.llm_eval


def decomposition_accuracy_evaluator(run, example) -> dict:
    """Evaluate whether decomposition output contains expected skills.

    From §15.1: Measures decomposition accuracy — do the generated skill
    nodes cover the expected competency areas?

    Returns:
        dict with "score" (0.0-1.0) and "reasoning" explanation.
    """
    predicted = run.outputs.get("skill_nodes", [])
    expected = example.outputs.get("expected_skills", [])

    if not expected:
        return {"score": 1.0, "reasoning": "No expected skills to compare."}

    predicted_names = {s.get("name", "").lower() for s in predicted}
    expected_names = {s.lower() for s in expected}

    overlap = predicted_names & expected_names
    coverage = len(overlap) / len(expected_names) if expected_names else 0

    return {
        "score": coverage,
        "reasoning": f"Covered {len(overlap)}/{len(expected_names)} expected skills. "
                     f"Missing: {expected_names - predicted_names}",
    }


def scoring_accuracy_evaluator(run, example) -> dict:
    """Evaluate whether assessment scoring falls within acceptable range.

    From §15.1: Assessment scoring accuracy vs human labels.

    Returns:
        dict with "score" (0.0 or 1.0) and "reasoning".
    """
    predicted_score = run.outputs.get("composite_score", 0)
    expected_min = example.outputs.get("expected_score_min", 0)
    expected_max = example.outputs.get("expected_score_max", 100)

    in_range = expected_min <= predicted_score <= expected_max

    return {
        "score": 1.0 if in_range else 0.0,
        "reasoning": f"Predicted {predicted_score}, expected [{expected_min}, {expected_max}]. "
                     f"{'Within' if in_range else 'Outside'} acceptable range.",
    }


class TestLLMEvaluation:
    """LangSmith evaluation tests — run separately from CI."""

    def test_decomposition_evaluator_logic(self):
        """Verify evaluator scoring logic works correctly."""
        from unittest.mock import MagicMock

        run = MagicMock()
        run.outputs = {
            "skill_nodes": [
                {"name": "Python Basics"},
                {"name": "Data Structures"},
                {"name": "API Design"},
            ]
        }

        example = MagicMock()
        example.outputs = {
            "expected_skills": ["Python Basics", "Data Structures", "Testing"]
        }

        result = decomposition_accuracy_evaluator(run, example)
        assert result["score"] == pytest.approx(2 / 3, abs=0.01)
        assert "Missing" in result["reasoning"]

    def test_scoring_evaluator_in_range(self):
        """Predicted score within expected range gets score 1.0."""
        from unittest.mock import MagicMock

        run = MagicMock()
        run.outputs = {"composite_score": 75}

        example = MagicMock()
        example.outputs = {"expected_score_min": 70, "expected_score_max": 85}

        result = scoring_accuracy_evaluator(run, example)
        assert result["score"] == 1.0

    def test_scoring_evaluator_out_of_range(self):
        """Predicted score outside expected range gets score 0.0."""
        from unittest.mock import MagicMock

        run = MagicMock()
        run.outputs = {"composite_score": 95}

        example = MagicMock()
        example.outputs = {"expected_score_min": 70, "expected_score_max": 85}

        result = scoring_accuracy_evaluator(run, example)
        assert result["score"] == 0.0

    @pytest.mark.skip(reason="Requires LangSmith dataset — run manually")
    async def test_run_full_decomposition_eval(self):
        """Run full decomposition evaluation against LangSmith dataset.

        Requires 'competency-decomposition-eval' dataset in LangSmith.
        Run manually: pytest tests/eval/ -m llm_eval -k decomposition --no-skip
        """
        from langsmith import evaluate
        from app.services.langsmith import get_eval_config

        config = get_eval_config(
            dataset_name="competency-decomposition-eval",
            experiment_name="decomp-accuracy",
        )

        async def predict(inputs: dict) -> dict:
            from app.agents.competency_architect import CompetencyArchitectAgent
            agent = CompetencyArchitectAgent()
            state = {
                "session_id": "eval-session",
                "competency_id": "eval-comp",
                "generated_content": inputs,
            }
            return await agent.process(state)

        results = evaluate(
            predict,
            data=config["dataset_name"],
            evaluators=[decomposition_accuracy_evaluator],
            experiment_prefix=config["experiment_prefix"],
            metadata=config["metadata"],
        )

        assert results is not None
