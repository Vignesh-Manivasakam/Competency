"""LangSmith observability integration.

From spec §17 Observability with LangSmith:
LangSmith provides per-agent dashboards showing: token usage, latency
percentiles, success rates, and full prompt/response trace for every invocation.

Environment variables (§16):
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=ls__...
  LANGCHAIN_PROJECT=competency-intelligence-mvp
"""
import structlog
from functools import lru_cache
from langsmith import Client
from langchain_core.tracers import LangChainTracer
from langchain_core.runnables import RunnableConfig

from app.core.config import settings

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def get_langsmith_client() -> Client | None:
    """Singleton LangSmith client — returns None if not configured.

    From §17: LangSmith is optional in development but required in staging/production.
    """
    if not settings.LANGCHAIN_API_KEY:
        logger.warning("langsmith_not_configured", reason="LANGCHAIN_API_KEY not set")
        return None
    return Client(
        api_key=settings.LANGCHAIN_API_KEY,
    )


def get_runnable_config(session_id: str, agent_name: str) -> RunnableConfig:
    """Create a RunnableConfig with LangSmith tracing callbacks.

    From spec §17 (Listing 19):
    Every agent invocation gets its own traced run with:
    - project_name: groups all traces under one LangSmith project
    - tags: per-agent and per-session tagging for dashboard filtering
    - metadata: structured fields for querying traces programmatically

    Args:
        session_id: The current learning session ID.
        agent_name: Name of the agent (e.g., "CompetencyArchitectAgent").

    Returns:
        RunnableConfig with tracing callbacks attached.
    """
    callbacks = []

    if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_API_KEY:
        callbacks.append(
            LangChainTracer(
                project_name=settings.LANGCHAIN_PROJECT,
                tags=[agent_name, f"session:{session_id}"],
            )
        )

    return RunnableConfig(
        callbacks=callbacks,
        metadata={
            "session_id": session_id,
            "agent": agent_name,
            "environment": settings.APP_ENV,
        },
    )


def get_eval_config(dataset_name: str, experiment_name: str) -> dict:
    """Configuration for LangSmith evaluation runs.

    From §15.1 (LLM Eval layer):
    Agent output quality evaluated via LangSmith Evaluators measuring
    decomposition accuracy and assessment scoring accuracy vs human labels.

    Returns:
        Dict with evaluation parameters for langsmith.evaluate().
    """
    return {
        "dataset_name": dataset_name,
        "experiment_prefix": experiment_name,
        "metadata": {
            "environment": settings.APP_ENV,
            "project": settings.LANGCHAIN_PROJECT,
        },
    }
