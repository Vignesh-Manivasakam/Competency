# app/agents/assessment_scoring.py
"""Assessment Scoring Agent — multi-dimensional response evaluation.

From spec §3:
Role: Evaluates employee responses across all scoring dimensions.
Produces a structured score and misconception flags.

Tools: None (pure LLM evaluation with structured output)
Memory Scope: None (stateless; results persisted by Learning State Manager)
LLM: GPT-4o (evaluator role; high accuracy in judging free-text)

Prompt Strategy: Rubric-based evaluation. System prompt includes
skill-specific rubric. Evaluates each dimension independently before
computing composite. Self-consistency check (evaluate twice, flag if
scores diverge > 15 points).
"""
import structlog
from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.schemas.assessment import ScoringOutput, DimensionScores
from app.services.llm_router import get_llm_structured
from app.services.langsmith import get_runnable_config
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an Assessment Scoring Agent for an AI-powered competency learning platform.

Your role is to evaluate an employee's response to a learning prompt across 5 dimensions.

## Scoring Dimensions (each scored 0-100):
1. **Accuracy**: Correctness of facts, concepts, and technical details
2. **Application**: Ability to apply knowledge to the specific context/scenario
3. **Reasoning**: Quality of logical reasoning, problem-solving approach
4. **Consistency**: Alignment with previously demonstrated knowledge
5. **Confidence**: Derived from response latency and language hedges (hedging words like "maybe", "I think", "not sure" reduce confidence)

## Skill Context
- Skill: {skill_name}
- Difficulty Level: {difficulty_level}/5
- Assessment Mode: {assessment_mode}
- Learning Strategy: {learning_strategy}

## Evaluation Rules
1. Evaluate EACH dimension independently before computing composite
2. The composite score is a weighted average:
   - Accuracy: 30%, Application: 25%, Reasoning: 25%, Consistency: 10%, Confidence: 10%
3. Identify specific misconceptions (incorrect mental models)
4. Provide actionable, specific corrective feedback
5. Consider response latency: very fast (<3s) or very slow (>60s) may indicate guessing or uncertainty
6. If the employee's response shows hedging language, reduce the confidence score

## Expected Response Schema
{expected_response_schema}

## Response Latency
{response_latency_ms}ms
"""


class AssessmentScoringAgent(BaseAgent):
    """Evaluates employee responses with multi-dimensional scoring."""

    def __init__(self, llm=None):
        super().__init__(agent_name="AssessmentScoringAgent")
        self.structured_llm = llm or get_llm_structured(
            self.agent_name, ScoringOutput
        )

    async def process(self, state: AgentState) -> dict:
        """Score an employee response."""
        session_id = state.get("session_id", "")
        content = state.get("generated_content", {})

        # Extract assessment inputs
        question = content.get("prompt_text", "")
        expected_schema = content.get("expected_response_schema", {})
        employee_response = state.get("messages", [])[-1].content if state.get("messages") else ""
        assessment_mode = content.get("assessment_mode", "conversational")
        skill_info = content.get("skill_node", {})
        response_latency = content.get("response_latency_ms", 0)

        # Build evaluation prompt
        system = SYSTEM_PROMPT.format(
            skill_name=skill_info.get("name", "Unknown"),
            difficulty_level=skill_info.get("difficulty_level", 3),
            assessment_mode=assessment_mode,
            learning_strategy=skill_info.get("learning_strategy", "conceptual"),
            expected_response_schema=str(expected_schema),
            response_latency_ms=response_latency,
        )

        user_prompt = (
            f"## Question/Prompt Given:\n{question}\n\n"
            f"## Employee's Response:\n{employee_response}\n\n"
            f"Evaluate this response according to the rubric."
        )

        config = self.get_config(session_id)

        # First evaluation
        result1: ScoringOutput = await self.structured_llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user_prompt)],
            config=config,
        )

        # Self-consistency check: evaluate twice, flag if diverge > 15 points
        result2: ScoringOutput = await self.structured_llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user_prompt)],
            config=config,
        )

        score_divergence = abs(result1.composite_score - result2.composite_score)
        consistency_flag = score_divergence > 15

        if consistency_flag:
            logger.warning(
                "score_divergence_detected",
                score1=result1.composite_score,
                score2=result2.composite_score,
                divergence=score_divergence,
            )
            # Average the two evaluations
            final_result = self._average_results(result1, result2)
        else:
            final_result = result1

        # Adjust confidence based on response latency
        if response_latency:
            if response_latency < 3000:  # < 3 seconds — might be guessing
                final_result.confidence_signal *= 0.7
            elif response_latency > 60000:  # > 60 seconds — uncertain
                final_result.confidence_signal *= 0.85

        assessment_dict = {
            "dimension_scores": final_result.dimension_scores.model_dump(),
            "composite_score": final_result.composite_score,
            "confidence_signal": final_result.confidence_signal,
            "misconceptions": [m.model_dump() for m in final_result.misconceptions],
            "feedback_points": final_result.feedback_points,
            "consistency_flagged": consistency_flag,
            "assessment_mode": assessment_mode,
        }

        logger.info(
            "assessment_scored",
            composite=final_result.composite_score,
            confidence=final_result.confidence_signal,
            misconceptions_count=len(final_result.misconceptions),
            consistency_flagged=consistency_flag,
        )

        return {
            "assessment_result": assessment_dict,
            "current_node": "score_response",
        }

    def _average_results(self, r1: ScoringOutput, r2: ScoringOutput) -> ScoringOutput:
        """Average two scoring results for consistency."""
        avg_dims = DimensionScores(
            accuracy=(r1.dimension_scores.accuracy + r2.dimension_scores.accuracy) / 2,
            application=(r1.dimension_scores.application + r2.dimension_scores.application) / 2,
            reasoning=(r1.dimension_scores.reasoning + r2.dimension_scores.reasoning) / 2,
            consistency=(r1.dimension_scores.consistency + r2.dimension_scores.consistency) / 2,
            confidence=(r1.dimension_scores.confidence + r2.dimension_scores.confidence) / 2,
        )
        return ScoringOutput(
            dimension_scores=avg_dims,
            composite_score=(r1.composite_score + r2.composite_score) / 2,
            confidence_signal=(r1.confidence_signal + r2.confidence_signal) / 2,
            misconceptions=r1.misconceptions + r2.misconceptions,
            feedback_points=list(set(r1.feedback_points + r2.feedback_points)),
            evaluation_rationale=f"Averaged: {r1.evaluation_rationale} | {r2.evaluation_rationale}",
        )


# LangGraph node function
assessment_scorer = AssessmentScoringAgent()


async def score_response_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Assessment Scoring Agent."""
    return await assessment_scorer(state)
