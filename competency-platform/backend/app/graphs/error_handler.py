# app/graphs/error_handler.py
"""Error handling node for all LangGraph workflows."""
import structlog
from app.graphs.state import AgentState

logger = structlog.get_logger()


async def handle_error(state: AgentState) -> dict:
    """Error handling sub-graph node."""
    error = state.get("error", "Unknown error")
    retry_count = state.get("retry_count", 0)
    fallback = state.get("fallback_triggered", False)

    logger.error(
        "workflow_error",
        error=error,
        retry_count=retry_count,
        fallback_triggered=fallback,
        session_id=state.get("session_id"),
        current_node=state.get("current_node"),
    )

    return {
        "error": error,
        "current_node": "error_handler",
        "next_action": "error",
    }
