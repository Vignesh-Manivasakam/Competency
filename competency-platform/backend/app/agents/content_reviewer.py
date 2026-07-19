# app/agents/content_reviewer.py
"""Content Reviewer Agent — quality gate before content delivery.

From spec §3:
Role: Quality gate before any generated content reaches the employee.
Checks accuracy, clarity, pedagogical soundness, and scope adherence.

Inputs: generated_content, skill_node, target_difficulty
Outputs: quality_score (0.0-1.0), decision (APPROVE/REVISE/REJECT),
         issues (list[QualityIssue]), revised_content

Thresholds:
  Score >= 0.82 → APPROVE
  Score 0.65-0.82 → REVISE (agent self-corrects)
  Score < 0.65 → REJECT (re-trigger Content Generator)

LLM: GPT-4o-mini (critic role; self-consistency via two evaluations)
Max Retry: Content Generator re-triggered max 2 times. Third failure → template.
"""
import structlog
from pydantic import BaseModel, Field
from app.agents.base import BaseAgent
from app.graphs.state import AgentState
from app.services.llm_router import get_llm_structured
from app.services.langsmith import get_runnable_config
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger()

THRESHOLD_APPROVE = 0.82
THRESHOLD_REVISE = 0.65


class QualityIssue(BaseModel):
    category: str  # accuracy, clarity, pedagogy, scope, difficulty
    description: str
    severity: str = "medium"  # low, medium, high


class ReviewOutput(BaseModel):
    quality_score: float = Field(..., ge=0.0, le=1.0)
    accuracy_score: float = Field(..., ge=0.0, le=1.0)
    clarity_score: float = Field(..., ge=0.0, le=1.0)
    pedagogy_score: float = Field(..., ge=0.0, le=1.0)
    scope_adherence_score: float = Field(..., ge=0.0, le=1.0)
    difficulty_alignment_score: float = Field(..., ge=0.0, le=1.0)
    issues: list[QualityIssue] = Field(default_factory=list)
    revised_content: str = ""
    review_rationale: str = ""


SYSTEM_PROMPT = """You are a Content Reviewer Agent for an AI-powered learning platform.

Your role is to evaluate generated learning content for quality before it reaches the learner.

## Evaluation Criteria (each scored 0.0-1.0):
1. **Accuracy**: Are facts, concepts, and technical details correct?
2. **Clarity**: Is the content clear, well-structured, and easy to understand?
3. **Pedagogical Soundness**: Does it follow good teaching principles? Progressive disclosure? Active learning?
4. **Scope Adherence**: Does it stay within the defined skill boundary? No drift to adjacent topics?
5. **Difficulty Alignment**: Does it match the target difficulty level {target_difficulty}/5?

## Skill Scope Boundary
- Skill Name: {skill_name}
- Skill Description: {skill_description}
- Target Difficulty: {target_difficulty}/5

## Quality Score Calculation
quality_score = average(accuracy, clarity, pedagogy, scope_adherence, difficulty_alignment)

## Decision Rules
- Score >= 0.82 → APPROVE
- Score 0.65-0.82 → REVISE (provide revised_content with fixes)
- Score < 0.65 → REJECT (too many issues to fix inline)

## If REVISE
Provide a corrected version in revised_content that fixes the identified issues.

## Output
Return scores, issues found, and revised_content if applicable.
"""


class ContentReviewerAgent(BaseAgent):
    """Quality gate for generated content."""

    def __init__(self, llm=None):
        super().__init__(agent_name="ContentReviewerAgent")
        self.structured_llm = llm or get_llm_structured(
            self.agent_name, ReviewOutput
        )

    async def process(self, state: AgentState) -> dict:
        """Review generated content for quality."""
        session_id = state.get("session_id", "")
        content = state.get("generated_content", {})
        skill_info = content.get("skill_node", {})
        target_difficulty = content.get("difficulty_level", 3)
        content_body = content.get("content_body", "")

        system = SYSTEM_PROMPT.format(
            skill_name=skill_info.get("name", "Unknown"),
            skill_description=skill_info.get("description", ""),
            target_difficulty=target_difficulty,
        )

        user_prompt = (
            f"## Content to Review:\n{content_body}\n\n"
            f"## Content Type: {content.get('content_type', 'explanation')}\n"
            f"## Interaction Prompts: {content.get('interaction_prompts', [])}\n\n"
            f"Evaluate this content according to the quality criteria."
        )

        config = self.get_config(session_id)

        # Two separate evaluations
        review1: ReviewOutput = await self.structured_llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user_prompt)],
            config=config,
        )
        review2: ReviewOutput = await self.structured_llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user_prompt)],
            config=config,
        )

        # Average the scores
        avg_score = (review1.quality_score + review2.quality_score) / 2

        # Determine decision
        if avg_score >= THRESHOLD_APPROVE:
            decision = "APPROVE"
        elif avg_score >= THRESHOLD_REVISE:
            decision = "REVISE"
        else:
            decision = "REJECT"

        # If REVISE, use the revised content from the review
        revised = review1.revised_content or review2.revised_content

        # Update generated_content with review result
        updated_content = dict(content)
        updated_content["review_decision"] = decision
        updated_content["quality_score"] = avg_score
        updated_content["review_issues"] = [i.model_dump() for i in review1.issues + review2.issues]

        if decision == "REVISE" and revised:
            updated_content["content_body"] = revised

        logger.info(
            "content_reviewed",
            quality_score=avg_score,
            decision=decision,
            issues_count=len(review1.issues),
            retry_count=state.get("retry_count", 0),
        )

        return {
            "generated_content": updated_content,
            "current_node": "review_content",
        }


# Template fallback content
TEMPLATE_CONTENT = {
    "explanation": "## {skill_name}\n\nThis skill covers the foundational concepts of {skill_name}. "
                   "Please discuss this topic with your tutor for a personalized learning experience.\n\n"
                   "### Key Points\n- Concept overview\n- Practical applications\n- Common misconceptions",
    "quiz": "## Quick Assessment: {skill_name}\n\n1. What is the primary purpose of {skill_name}?\n"
            "2. Describe a real-world application.\n3. What are common mistakes beginners make?",
    "scenario": "## Scenario: {skill_name}\n\nYou are working on a project that requires {skill_name}. "
                "Your team lead has asked you to evaluate the current approach. What would you consider?",
    "dialogue": "Let's discuss {skill_name} together. Can you start by telling me what you already know about this topic?",
}


def get_template_content(content_type: str, skill_name: str) -> str:
    """Fallback template content when generation fails 3 times."""
    template = TEMPLATE_CONTENT.get(content_type, TEMPLATE_CONTENT["explanation"])
    return template.format(skill_name=skill_name)


# LangGraph node function
content_reviewer = ContentReviewerAgent()


async def review_content_node(state: AgentState) -> dict:
    """LangGraph node wrapper for the Content Reviewer Agent."""
    return await content_reviewer(state)
