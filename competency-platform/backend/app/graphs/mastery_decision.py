# app/graphs/mastery_decision.py
"""Mastery decision workflow — stub. Full impl in Plan 14."""
from langgraph.graph import StateGraph, END
from app.graphs.state import AgentState


def build_mastery_decision_graph(checkpointer):
    graph = StateGraph(AgentState)
    graph.add_node("placeholder", lambda state: state)
    graph.set_entry_point("placeholder")
    graph.add_edge("placeholder", END)
    return graph.compile(checkpointer=checkpointer)
