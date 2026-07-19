# app/services/langsmith.py
"""LangSmith observability configuration for all agent invocations."""
from langsmith import Client
from langchain_core.tracers import LangChainTracer
from langchain_core.runnables import RunnableConfig
from app.core.config import settings


def get_runnable_config(session_id: str, agent_name: str) -> RunnableConfig:
    """Standard runnable config for all agent invocations."""
    return RunnableConfig(
        callbacks=[LangChainTracer(
            project_name="competency-intelligence-mvp",
            tags=[agent_name, f"session:{session_id}"],
        )],
        metadata={
            "session_id": session_id,
            "agent": agent_name,
            "environment": settings.APP_ENV,
        },
    )
