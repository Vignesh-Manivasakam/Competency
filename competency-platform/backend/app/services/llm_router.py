# app/services/llm_router.py
"""LLM model selection and routing per agent."""
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from app.core.config import settings

# Agent-to-model mapping from spec §18.2
AGENT_MODEL_MAP = {
    "CompetencyArchitectAgent": "gpt-4o",
    "LearningPathDesignerAgent": "gpt-4o-mini",
    "ContentGeneratorAgent": "gpt-4o-mini",
    "AdaptiveTutorAgent": "gpt-4o",
    "AssessmentScoringAgent": "gpt-4o",
    "MasteryEvaluationAgent": "gpt-4o",
    "ContentReviewerAgent": "gpt-4o-mini",
}

# Content-type specific overrides for Content Generator
CONTENT_TYPE_MODEL_MAP = {
    "explanation": "gpt-4o-mini",
    "quiz": "gpt-4o-mini",
    "scenario": "gpt-4o",
    "dialogue": "gpt-4o",
}


def get_llm(agent_name: str, temperature: float = 0.3):
    """Get the appropriate LLM for an agent.
    
    Primary: OpenAI (model from AGENT_MODEL_MAP)
    Fallback: Anthropic Claude Sonnet 4.6
    """
    model = AGENT_MODEL_MAP.get(agent_name, "gpt-4o-mini")
    try:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            timeout=30,
            max_retries=2,
        )
    except Exception:
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            temperature=temperature,
            timeout=30,
        )


def get_llm_structured(agent_name: str, schema: type):
    """Get LLM configured for structured (JSON schema) output.
    
    Used by agents that need typed responses:
    - CompetencyArchitectAgent (skill decomposition)
    - AssessmentScoringAgent (dimension scores)
    - MasteryEvaluationAgent (mastery decisions)
    """
    llm = get_llm(agent_name, temperature=0.1)
    return llm.with_structured_output(schema, method="json_schema")


def get_llm_for_content(content_type: str, temperature: float = 0.7):
    """Get model based on content type (Content Generator specific)."""
    model = CONTENT_TYPE_MODEL_MAP.get(content_type, "gpt-4o-mini")
    try:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            timeout=30,
            max_retries=2,
        )
    except Exception:
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            temperature=temperature,
            timeout=30,
        )
