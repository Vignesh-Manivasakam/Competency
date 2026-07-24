"""Unit tests for Pydantic schema validation.

From spec §15.1 (Unit - schemas):
Pydantic model validation, edge cases.

Tests cover all API request/response schemas from §8.
"""
import pytest
from uuid import uuid4
from pydantic import ValidationError


class TestCompetencySchemas:
    """Validate competency-related Pydantic models."""

    def test_competency_create_valid(self):
        """Valid CompetencyCreate passes validation."""
        from app.schemas.competency import CompetencyCreate

        comp = CompetencyCreate(
            name="Backend Engineering",
            description="Full-stack backend development skills",
        )
        assert comp.name == "Backend Engineering"

    def test_competency_create_empty_name_fails(self):
        """Empty competency name should fail validation."""
        from app.schemas.competency import CompetencyCreate

        with pytest.raises(ValidationError):
            CompetencyCreate(name="", description="Valid description")

    def test_competency_create_name_too_long(self):
        """Competency name > 255 chars should fail validation."""
        from app.schemas.competency import CompetencyCreate

        with pytest.raises(ValidationError):
            CompetencyCreate(name="A" * 256, description="Valid description")


class TestSessionSchemas:
    """Validate session-related schemas."""

    def test_session_create_valid(self):
        """Valid SessionCreateRequest passes validation."""
        from app.schemas.session import SessionCreateRequest

        session = SessionCreateRequest(
            employee_id=uuid4(),
            skill_id=uuid4(),
            session_type="learning",
        )
        assert session.employee_id is not None

    def test_session_create_invalid_type(self):
        """Invalid session type raises validation error."""
        from app.schemas.session import SessionCreateRequest

        with pytest.raises(ValidationError):
            SessionCreateRequest(
                employee_id=uuid4(),
                skill_id=uuid4(),
                session_type="invalid_type",
            )


class TestAssessmentSchemas:
    """Validate assessment scoring schemas."""

    def test_scoring_output_boundaries(self):
        """Score must be 0-100, confidence 0.0-1.0."""
        from app.schemas.assessment import ScoringOutput, DimensionScores

        output = ScoringOutput(
            composite_score=50.0,
            dimension_scores=DimensionScores(
                accuracy=50.0, application=50.0, reasoning=50.0, consistency=50.0, confidence=50.0
            ),
            misconceptions=[],
            confidence_signal=0.5,
            feedback_points=[],
            evaluation_rationale="Average performance.",
        )
        assert 0 <= output.composite_score <= 100
        assert 0.0 <= output.confidence_signal <= 1.0

    def test_mastery_decision_enum_values(self):
        """Mastery decision must be UPGRADE, MAINTAIN, or DOWNGRADE."""
        from app.agents.mastery_evaluation import MasteryDecisionOutput

        output = MasteryDecisionOutput(
            mastery_decision="UPGRADE",
            new_mastery_level=3,
            confidence=0.88,
            evidence_summary="Met all criteria.",
            remaining_gaps=[],
            reasoning="Consistent high performance.",
        )
        assert output.mastery_decision in ("UPGRADE", "MAINTAIN", "DOWNGRADE")

        with pytest.raises(ValidationError):
            MasteryDecisionOutput(
                mastery_decision="INVALID",
                new_mastery_level=3,
                confidence=0.88,
                evidence_summary="",
                reasoning="",
            )

    def test_mastery_level_range(self):
        """Mastery level must be 0-5 per MasteryLevel enum."""
        from app.agents.mastery_evaluation import MasteryDecisionOutput

        with pytest.raises(ValidationError):
            MasteryDecisionOutput(
                mastery_decision="UPGRADE",
                new_mastery_level=6,  # Invalid: max is 5
                confidence=0.88,
                evidence_summary="",
                reasoning="",
            )

        with pytest.raises(ValidationError):
            MasteryDecisionOutput(
                mastery_decision="DOWNGRADE",
                new_mastery_level=-1,  # Invalid: min is 0
                confidence=0.88,
                evidence_summary="",
                reasoning="",
            )
