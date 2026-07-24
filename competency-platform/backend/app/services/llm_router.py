# app/services/llm_router.py
"""LLM model selection and routing per agent with NVIDIA NIM integration.

Supports NVIDIA NIM API (base_url: https://integrate.api.nvidia.com/v1)
with fallback to OpenAI and Anthropic.
"""
import os
import structlog
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from app.core.config import settings

logger = structlog.get_logger()

# Agent-to-model mapping optimized for NVIDIA NIM (Meta Llama 3.1 70B & 8B)
AGENT_MODEL_MAP_NVIDIA = {
    "CompetencyArchitectAgent": "meta/llama-3.1-70b-instruct",
    "LearningPathDesignerAgent": "meta/llama-3.1-8b-instruct",
    "ContentGeneratorAgent": "meta/llama-3.1-8b-instruct",
    "AdaptiveTutorAgent": "meta/llama-3.1-70b-instruct",
    "AssessmentScoringAgent": "meta/llama-3.1-70b-instruct",
    "MasteryEvaluationAgent": "meta/llama-3.1-70b-instruct",
    "ContentReviewerAgent": "meta/llama-3.1-8b-instruct",
}

# Fallback OpenAI mapping
AGENT_MODEL_MAP_OPENAI = {
    "CompetencyArchitectAgent": "gpt-4o",
    "LearningPathDesignerAgent": "gpt-4o-mini",
    "ContentGeneratorAgent": "gpt-4o-mini",
    "AdaptiveTutorAgent": "gpt-4o",
    "AssessmentScoringAgent": "gpt-4o",
    "MasteryEvaluationAgent": "gpt-4o",
    "ContentReviewerAgent": "gpt-4o-mini",
}

# Content-type specific overrides for Content Generator
CONTENT_TYPE_MODEL_MAP_NVIDIA = {
    "explanation": "meta/llama-3.1-8b-instruct",
    "quiz": "meta/llama-3.1-8b-instruct",
    "scenario": "meta/llama-3.1-70b-instruct",
    "dialogue": "meta/llama-3.1-70b-instruct",
}

CONTENT_TYPE_MODEL_MAP_OPENAI = {
    "explanation": "gpt-4o-mini",
    "quiz": "gpt-4o-mini",
    "scenario": "gpt-4o",
    "dialogue": "gpt-4o",
}


def get_llm(agent_name: str, temperature: float = 0.3):
    """Get the appropriate LLM for an agent.
    
    Priority 1: NVIDIA NIM (Meta Llama 3.1 70B / 8B)
    Priority 2: OpenAI (GPT-4o / GPT-4o-mini)
    Priority 3: Anthropic (Claude Sonnet)
    """
    nvidia_key = settings.NVIDIA_API_KEY or os.getenv("NVIDIA_API_KEY", "")
    
    if settings.USE_NVIDIA_NIM and nvidia_key and not nvidia_key.startswith("sk-test"):
        model = AGENT_MODEL_MAP_NVIDIA.get(agent_name, "meta/llama-3.1-70b-instruct")
        logger.info("using_nvidia_nim_llm", agent=agent_name, model=model)
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=nvidia_key,
            base_url=settings.NVIDIA_BASE_URL,
            timeout=30,
            max_retries=2,
        )

    # Fallback to standard OpenAI
    model = AGENT_MODEL_MAP_OPENAI.get(agent_name, "gpt-4o-mini")
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
    nvidia_key = settings.NVIDIA_API_KEY or os.getenv("NVIDIA_API_KEY", "")
    
    if settings.USE_NVIDIA_NIM and nvidia_key and not nvidia_key.startswith("sk-test"):
        model = CONTENT_TYPE_MODEL_MAP_NVIDIA.get(content_type, "meta/llama-3.1-70b-instruct")
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=nvidia_key,
            base_url=settings.NVIDIA_BASE_URL,
            timeout=30,
            max_retries=2,
        )

    model = CONTENT_TYPE_MODEL_MAP_OPENAI.get(content_type, "gpt-4o-mini")
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
