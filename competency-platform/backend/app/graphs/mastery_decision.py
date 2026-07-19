# app/graphs/mastery_decision.py
"""Mastery decision LangGraph workflow.

From spec §3 (Orchestrator):
mastery_decision_graph: Mastery Evaluation → State Manager → Notify Manager
"""
from langgraph.graph import StateGraph, END
from app.graphs.state import AgentState
from app.agents.mastery_evaluation import check_mastery_node
from app.graphs.error_handler import handle_error


async def commit_mastery(state: AgentState) -> dict:
    """Commit mastery decision to PostgreSQL via Learning State Manager."""
    decision = state.get("mastery_decision", {})
    if decision and decision.get("mastery_decision") == "UPGRADE":
        return {"current_node": "commit_mastery", "next_action": "notify"}
    return {"current_node": "commit_mastery", "next_action": "complete"}


async def notify_manager(state: AgentState) -> dict:
    """Notify manager of mastery change (placeholder for notification system)."""
    return {"current_node": "notify_manager"}


def build_mastery_decision_graph(checkpointer):
    graph = StateGraph(AgentState)
    graph.add_node("evaluate", check_mastery_node)
    graph.add_node("commit", commit_mastery)
    graph.add_node("notify", notify_manager)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("evaluate")
    graph.add_edge("evaluate", "commit")
    graph.add_conditional_edges("commit", lambda s: s.get("next_action", "complete"), {
        "notify": "notify",
        "complete": END,
    })
    graph.add_edge("notify", END)
    graph.add_edge("handle_error", END)

    return graph.compile(checkpointer=checkpointer)
