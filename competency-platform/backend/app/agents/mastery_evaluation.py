# app/agents/mastery_evaluation.py
"""Mastery Evaluation Agent — evidence-based mastery decisions.

From spec §3:
Role: Determines whether a skill mastery level should be upgraded based
on accumulated evidence. Makes the final mastery decision.

Inputs: employee_id, skill_id, recent_assessments (last 5-10),
        current_mastery_level (0-5), error_history
Outputs: mastery_decision (UPGRADE/MAINTAIN/DOWNGRADE), new_mastery_level,
         confidence, evidence_summary, remaining_gaps

Tools: PostgreSQL (assessment history), Neo4j (check prerequisites)
Memory Scope: Long-term read (historical assessment results)
LLM: GPT-4o (analytical role; reasoning across data points)

Decision Rules (hard-coded, LLM confirms):
  Score >= threshold for 3 consecutive sessions
  AND error rate < 12%
  AND confidence >= 0.80
  = upgrade candidate

MasteryLevel: NOT_STARTED=0, AWARENESS=1, DEVELOPING=2, PROFICIENT=3, ADVANCED=4, MASTERED=5
"""
import structlog
from pydantic import BaseModel, Field
from typing import Optional
from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.services.llm_router import get_llm_structured
from app.services.langsmith import get_runnable_config
from app.services.skill_graph import SkillGraphService
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

# Mastery thresholds per level (score needed to upgrade TO this level)
MASTERY_THRESHOLDS = {
    1: 30.0,   # → AWARENESS
    2: 50.0,   # → DEVELOPING
    3: 65.0,   # → PROFICIENT
    4: 80.0,   # → ADVANCED
    5: 92.0,   # → MASTERED
}

CONSECUTIVE_SESSIONS_REQUIRED = 3
MAX_ERROR_RATE = 0.12  # 12%
MIN_CONFIDENCE = 0.80


class MasteryDecisionOutput(BaseModel):
    mastery_decision: str = Field(..., pattern="^(UPGRADE|MAINTAIN|DOWNGRADE)$")
    new_mastery_level: int = Field(..., ge=0, le=5)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str
    remaining_gaps: list[str] = Field(default_factory=list)
    reasoning: str


SYSTEM_PROMPT = """You are a Mastery Evaluation Agent. Analyze the evidence and confirm or adjust the proposed mastery decision.

## Decision Rules (Hard-Coded)
- UPGRADE if: Score >= threshold for {consecutive_required} consecutive sessions AND error rate < 12% AND confidence >= 0.80
- DOWNGRADE if: Score consistently below current level threshold for 3+ sessions OR error rate > 25%
- MAINTAIN otherwise

## Current State
- Employee: {employee_id}
- Skill: {skill_name}
- Current Mastery Level: {current_level}/5 ({level_name})
- Threshold for next level: {next_threshold}

## Recent Assessment Results (Last {assessment_count})
{assessment_summary}

## Error History
{error_history}

## Prerequisite Status
{prerequisite_status}

## Your Analysis
1. Review the score trend (improving, stable, declining?)
2. Check if upgrade/downgrade rules are met
3. Identify remaining knowledge gaps
4. Provide confidence in your decision
5. Write a clear evidence summary for manager review
"""


class MasteryEvaluationAgent(BaseAgent):
    """Evidence-based mastery level decisions."""

    def __init__(self, llm=None):
        super().__init__(agent_name="MasteryEvaluationAgent")
        self.custom_llm = llm
        self.structured_llm = llm or get_llm_structured(
            self.agent_name, MasteryDecisionOutput
        )

    async def process(self, state: AgentState) -> dict:
        session_id = state.get("session_id", "")
        employee_id = state.get("employee_id", "")
        skill_id = state.get("skill_id", "")

        # Get assessment data from state
        scores = state.get("session_scores", [])
        current_level = 0
        assessment_data = state.get("generated_content", {})
        recent_assessments = assessment_data.get("recent_assessments", scores)
        error_history = assessment_data.get("error_history", [])

        # Hard-coded rule check first
        proposed_decision = self._apply_rules(
            recent_assessments, current_level, error_history
        )

        # Check prerequisites in Neo4j
        prereq_status = await SkillGraphService.check_all_prerequisites_mastered(
            employee_id, skill_id
        )

        # If upgrade proposed but prerequisites not met, maintain
        if proposed_decision["decision"] == "UPGRADE" and not prereq_status.get("all_prerequisites_met", True):
            proposed_decision["decision"] = "MAINTAIN"
            proposed_decision["reason"] = "Prerequisites not yet mastered"

        # LLM confirms/adjusts the decision
        level_names = ["Not Started", "Awareness", "Developing", "Proficient", "Advanced", "Mastered"]
        next_level = min(current_level + 1, 5)

        system = SYSTEM_PROMPT.format(
            consecutive_required=CONSECUTIVE_SESSIONS_REQUIRED,
            employee_id=employee_id,
            skill_name=assessment_data.get("skill_name", "Unknown"),
            current_level=current_level,
            level_name=level_names[current_level],
            next_threshold=MASTERY_THRESHOLDS.get(next_level, 100),
            assessment_count=len(recent_assessments),
            assessment_summary=self._format_assessments(recent_assessments),
            error_history=str(error_history),
            prerequisite_status=str(prereq_status),
        )

        config = self.get_config(session_id)
        
        # Resolve LLM router dynamically
        llm = self.custom_llm or self.structured_llm

        result: MasteryDecisionOutput = await llm.ainvoke(
            [SystemMessage(content=system),
             HumanMessage(content=f"Evaluate mastery for skill {skill_id}. "
                         f"Proposed decision: {proposed_decision['decision']}")],
            config=config,
        )

        decision_dict = {
            "mastery_decision": result.mastery_decision,
            "new_mastery_level": result.new_mastery_level,
            "confidence": result.confidence,
            "evidence_summary": result.evidence_summary,
            "remaining_gaps": result.remaining_gaps,
            "employee_id": employee_id,
            "skill_id": skill_id,
            "session_id": session_id,
        }

        logger.info(
            "mastery_evaluated",
            decision=result.mastery_decision,
            new_level=result.new_mastery_level,
            confidence=result.confidence,
        )

        return {
            "mastery_decision": decision_dict,
            "current_node": "check_mastery",
            "next_action": result.mastery_decision.lower(),
        }

    def _apply_rules(self, assessments: list, current_level: int, errors: list) -> dict:
        """Apply hard-coded decision rules before LLM confirmation."""
        if len(assessments) < CONSECUTIVE_SESSIONS_REQUIRED:
            return {"decision": "MAINTAIN", "reason": "Insufficient data"}

        next_level = min(current_level + 1, 5)
        threshold = MASTERY_THRESHOLDS.get(next_level, 100)

        # Check consecutive scores above threshold
        recent = assessments[-CONSECUTIVE_SESSIONS_REQUIRED:]
        scores = [a.get("composite_score", 0) if isinstance(a, dict) else 0 for a in recent]
        all_above = all(s >= threshold for s in scores)

        # Calculate error rate
        total_interactions = sum(a.get("interaction_count", 1) if isinstance(a, dict) else 1 for a in assessments)
        total_errors = len(errors)
        error_rate = total_errors / max(total_interactions, 1)

        # Average confidence
        confidences = [a.get("confidence_signal", 0.5) if isinstance(a, dict) else 0.5 for a in recent]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        if all_above and error_rate < MAX_ERROR_RATE and avg_confidence >= MIN_CONFIDENCE:
            return {"decision": "UPGRADE", "reason": "All criteria met"}

        # Check for downgrade
        if len(scores) >= 3 and all(s < threshold * 0.6 for s in scores):
            return {"decision": "DOWNGRADE", "reason": "Consistent underperformance"}

        return {"decision": "MAINTAIN", "reason": "Criteria not fully met"}

    def _format_assessments(self, assessments: list) -> str:
        if not assessments:
            return "No assessments available."
        lines = []
        for i, a in enumerate(assessments[-10:]):  # Last 10
            if isinstance(a, dict):
                lines.append(f"  Session {i+1}: Score={a.get('composite_score', '?')}, "
                           f"Confidence={a.get('confidence_signal', '?')}")
        return "\n".join(lines) or "No formatted assessments."


# LangGraph node
mastery_evaluator = MasteryEvaluationAgent()


async def check_mastery_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Mastery Evaluation Agent."""
    return await mastery_evaluator(state)
