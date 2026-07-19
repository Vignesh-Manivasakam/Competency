# app/graphs/state.py
"""Core agent state shared across all LangGraph workflows."""
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # Identifiers
    session_id: str
    employee_id: str
    skill_id: Optional[str]
    competency_id: Optional[str]

    # Workflow control
    workflow_type: str  # "decomposition" | "baseline" | "learning" | "mastery"
    current_node: str
    next_action: str  # determined by each node's output

    # Learning session state
    messages: Annotated[list, add_messages]  # LangGraph message accumulator
    current_proficiency: float
    interaction_count: int
    session_scores: list[dict]

    # Agent outputs (passed between nodes)
    generated_content: Optional[dict]
    assessment_result: Optional[dict]
    mastery_decision: Optional[dict]
    skill_graph: Optional[dict]

    # Error handling
    error: Optional[str]
    retry_count: int
    fallback_triggered: bool
