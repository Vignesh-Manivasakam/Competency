# app/agents/base.py
"""Base agent class — all 9 agents extend this."""
import abc
import asyncio
import structlog
from typing import Any, Optional
from app.graphs.state import AgentState
from app.services.llm_router import get_llm, get_llm_structured
from app.services.langsmith import get_runnable_config

logger = structlog.get_logger()


class BaseAgent(abc.ABC):
    """Abstract base class for all MVP agents."""

    def __init__(self, agent_name: str | None = None):
        self.agent_name = agent_name or self.__class__.__name__
        self.llm = get_llm(self.agent_name)
        self.logger = logger.bind(agent=self.agent_name)

    def get_structured_llm(self, schema: type):
        """Get LLM with structured output for this agent."""
        return get_llm_structured(self.agent_name, schema)

    def get_config(self, session_id: str) -> dict:
        """Get LangSmith runnable config for tracing."""
        return get_runnable_config(session_id, self.agent_name)

    @abc.abstractmethod
    async def process(self, state: AgentState) -> dict:
        """Process the agent state and return updates."""
        ...

    async def __call__(self, state: AgentState) -> dict:
        """LangGraph node invocation wrapper with error handling."""
        self.logger.info(
            "agent_invoked",
            session_id=state.get("session_id"),
            workflow_type=state.get("workflow_type"),
        )
        try:
            result = await self.process(state)
            result["current_node"] = self.agent_name
            result["error"] = None
            return result
        except Exception as e:
            retry_count = state.get("retry_count", 0)
            max_retries = 3
            backoff_seconds = [1, 2, 4]

            if retry_count < max_retries:
                wait = backoff_seconds[min(retry_count, len(backoff_seconds) - 1)]
                self.logger.warning(
                    "agent_retry",
                    error=str(e),
                    retry=retry_count + 1,
                    backoff_seconds=wait,
                )
                await asyncio.sleep(wait)
                return {
                    "error": str(e),
                    "retry_count": retry_count + 1,
                    "current_node": self.agent_name,
                }
            else:
                self.logger.error(
                    "agent_failed",
                    error=str(e),
                    retries_exhausted=True,
                )
                return {
                    "error": str(e),
                    "retry_count": retry_count,
                    "fallback_triggered": True,
                    "current_node": self.agent_name,
                }
