# app/graphs/baseline_assessment.py
"""Baseline assessment workflow — stub. Full impl in Plan 15."""
from langgraph.graph import StateGraph, END
from app.graphs.state import AgentState


def build_baseline_assessment_graph(checkpointer):
    graph = StateGraph(AgentState)
    graph.add_node("placeholder", lambda state: state)
    graph.set_entry_point("placeholder")
    graph.add_edge("placeholder", END)
    return graph.compile(checkpointer=checkpointer)
