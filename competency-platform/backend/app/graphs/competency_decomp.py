# app/graphs/competency_decomp.py
"""Competency decomposition LangGraph workflow.

From spec §3 (Orchestrator):
competency_decomposition_graph:
Manager creates competency → Architect → Neo4j → Manager validation
"""
from langgraph.graph import StateGraph, END
from app.graphs.state import AgentState
from app.agents.competency_architect import competency_architect_node
from app.services.skill_graph import SkillGraphService
from app.graphs.error_handler import handle_error


async def save_to_neo4j(state: AgentState) -> dict:
    """Save decomposed skills to Neo4j after architect completes."""
    skill_graph = state.get("skill_graph", {})
    if not skill_graph:
        return {"error": "No skill graph to save"}

    await SkillGraphService.create_competency_subgraph(
        competency_id=skill_graph["competency_id"],
        competency_name=state.get("generated_content", {}).get("name", ""),
        version="1.0",
        status="under_review",
        tenant_id="",  # Set from context
        skill_nodes=skill_graph["skill_nodes"],
        skill_edges=skill_graph["skill_edges"],
    )
    return {"current_node": "save_to_neo4j", "next_action": "complete"}


def route_after_architect(state: AgentState) -> str:
    if state.get("error"):
        return "error"
    return "save"


def build_competency_decomp_graph(checkpointer):
    graph = StateGraph(AgentState)

    graph.add_node("architect", competency_architect_node)
    graph.add_node("save_to_neo4j", save_to_neo4j)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("architect")
    graph.add_conditional_edges("architect", route_after_architect, {
        "save": "save_to_neo4j",
        "error": "handle_error",
    })
    graph.add_edge("save_to_neo4j", END)
    graph.add_edge("handle_error", END)

    return graph.compile(checkpointer=checkpointer)
