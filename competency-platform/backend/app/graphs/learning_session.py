# app/graphs/learning_session.py
"""Learning Session LangGraph — the core adaptive learning loop.

From spec §4.2 (Listing 2):
Implements the full learning session workflow:
  load_state → generate_content → review_content → deliver_to_tutor
  → [wait for employee response] → score_response → update_state
  → check_mastery → [route: upgrade/continue/session_end]

From spec §21.3 (Flow 3):
1. POST /sessions creates session → returns session_id
2. Frontend connects WebSocket /sessions/{id}/ws?token={jwt}
3. LangGraph loads employee state; Path Designer selects module
4. Content Generator generates; Reviewer approves
5. Employee responds via WebSocket
6. Assessment Scoring evaluates; state updated
7. Loop until session_complete or mastery threshold
8. On mastery upgrade: mastery_updated event sent

Graph Topology:
  load_state ──→ generate_content ──→ review_content ──→[route_after_review]
                                         ├─ APPROVE → deliver_to_tutor
                                         ├─ REVISE  → generate_content (loop)
                                         └─ ERROR   → handle_error

  deliver_to_tutor ──→ score_response ──→ update_state ──→[route_after_score]
                                            ├─ continue     → generate_content
                                            ├─ reinforce    → generate_content
                                            ├─ check_mastery→ check_mastery
                                            └─ session_end  → END

  check_mastery ──→[route_after_mastery]
                     ├─ upgrade     → END (with mastery_updated event)
                     ├─ continue    → generate_content
                     └─ session_end → END
"""
import structlog
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from app.graphs.state import AgentState

# Import agent node functions from their respective plans
from app.agents.learning_path_designer import design_path_node
from app.agents.content_generator import generate_content_node
from app.agents.content_reviewer import review_content_node
from app.agents.adaptive_tutor import prepare_interaction_node
from app.agents.assessment_scoring import score_response_node
from app.agents.mastery_evaluation import check_mastery_node
from app.agents.learning_state_manager import (
    load_state,
    update_state,
)
from app.graphs.error_handler import handle_error

logger = structlog.get_logger()

# ──────────────────────────────────────────────
# Maximum limits (safety bounds)
# ──────────────────────────────────────────────
MAX_INTERACTIONS_PER_SESSION = 25
MAX_CONTENT_REVISIONS = 3
MASTERY_CHECK_INTERVAL = 5  # Check mastery every N interactions


# ──────────────────────────────────────────────
# Routing Functions
# ──────────────────────────────────────────────

def route_after_review(state: AgentState) -> str:
    """Route after Content Reviewer evaluates generated content.
    
    From §4.2: Three possible outcomes:
    - APPROVE: Content quality passes → deliver to tutor
    - REVISE:  Content needs improvement → loop back to generator
    - ERROR:   Review failed entirely → error handler
    
    Safety: Caps revision loops at MAX_CONTENT_REVISIONS to prevent
    infinite generate→review→revise loops.
    """
    review_result = state.get("generated_content", {}).get("review_result", {})
    # Defaulting to APPROVE if not present to ensure progress
    review_decision = state.get("generated_content", {}).get("review_decision") or review_result.get("decision", "APPROVE")
    revision_count = state.get("generated_content", {}).get("revision_count", 0)
    error = state.get("error")

    if error:
        logger.warning("route_after_review_error", error=error)
        return "ERROR"

    if review_decision == "REVISE" and revision_count < MAX_CONTENT_REVISIONS:
        logger.info(
            "content_revision_requested",
            revision_count=revision_count + 1,
            max_revisions=MAX_CONTENT_REVISIONS,
        )
        return "REVISE"

    if review_decision == "REVISE" and revision_count >= MAX_CONTENT_REVISIONS:
        logger.warning(
            "content_revision_limit_reached",
            revision_count=revision_count,
        )
        # Accept the content as-is after max revisions
        return "APPROVE"

    return "APPROVE"


def route_after_score(state: AgentState) -> str:
    """Route after Assessment Scoring and state update.
    
    From §4.2: Determines the next loop action based on
    tutor's decision and interaction count:
    - continue:      Keep going with new content
    - reinforce:     Same topic, different angle (difficulty -1)
    - check_mastery: Enough evidence to evaluate mastery upgrade
    - session_end:   Max interactions reached or COMPLETE action
    """
    next_action = state.get("next_action", "continue")
    interaction_count = state.get("interaction_count", 0)
    error = state.get("error")

    if error:
        return "session_end"

    # Check if max interactions reached
    if interaction_count >= MAX_INTERACTIONS_PER_SESSION:
        logger.info(
            "max_interactions_reached",
            count=interaction_count,
            max=MAX_INTERACTIONS_PER_SESSION,
        )
        return "check_mastery"

    # Tutor decided session is complete
    if next_action in ("COMPLETE", "complete"):
        return "check_mastery"

    # Periodic mastery check
    if (interaction_count > 0
            and interaction_count % MASTERY_CHECK_INTERVAL == 0):
        return "check_mastery"

    # Escalation → end session, flag for human review
    if next_action in ("ESCALATE", "escalate"):
        return "session_end"

    # CONTINUE, REINFORCE, ADVANCE all generate new content
    if next_action in ("REINFORCE", "reinforce"):
        return "reinforce"

    return "continue"


def route_after_mastery(state: AgentState) -> str:
    """Route after Mastery Evaluation Agent decision.
    
    From §4.2: Three outcomes:
    - upgrade:     Mastery upgraded → end session (celebration!)
    - continue:    Not ready for upgrade → keep learning
    - session_end: Downgrade or session should end
    """
    mastery_decision = state.get("mastery_decision", {})
    decision = mastery_decision.get("mastery_decision", "MAINTAIN")
    interaction_count = state.get("interaction_count", 0)

    if decision == "UPGRADE":
        logger.info(
            "mastery_upgrade_routed",
            new_level=mastery_decision.get("new_mastery_level"),
            confidence=mastery_decision.get("confidence"),
        )
        return "upgrade"

    if decision == "DOWNGRADE":
        return "session_end"

    # MAINTAIN — keep learning if under interaction limit
    if interaction_count < MAX_INTERACTIONS_PER_SESSION:
        return "continue"

    return "session_end"


# ──────────────────────────────────────────────
# Graph Builder
# ──────────────────────────────────────────────

def build_learning_session_graph(checkpointer) -> CompiledStateGraph:
    """Build the full Learning Session LangGraph.
    
    From spec §4.2 (Listing 2):
    This is the primary workflow graph that drives every adaptive
    learning session. It connects all 7 agent node functions in
    the correct topology with conditional routing edges.
    
    Args:
        checkpointer: AsyncPostgresSaver from Plan 5 — enables
                      session resume after crashes, full audit trail,
                      and time-travel debugging.
    
    Returns:
        CompiledGraph ready for ainvoke() with thread_id checkpointing.
    """
    graph = StateGraph(AgentState)

    # ── Register all nodes (from §4.2 Listing 2) ──
    graph.add_node("load_state", load_state)
    graph.add_node("generate_content", generate_content_node)
    graph.add_node("review_content", review_content_node)
    graph.add_node("deliver_to_tutor", prepare_interaction_node)
    graph.add_node("score_response", score_response_node)
    graph.add_node("update_state", update_state)
    graph.add_node("check_mastery", check_mastery_node)
    graph.add_node("handle_error", handle_error)

    # ── Entry point ──
    graph.set_entry_point("load_state")

    # ── Linear edges ──
    graph.add_edge("load_state", "generate_content")
    graph.add_edge("generate_content", "review_content")
    graph.add_edge("deliver_to_tutor", "score_response")
    graph.add_edge("score_response", "update_state")

    # ── Conditional edge: after review ──
    graph.add_conditional_edges(
        "review_content",
        route_after_review,
        {
            "APPROVE": "deliver_to_tutor",
            "REVISE": "generate_content",   # Loop back for revision
            "ERROR": "handle_error",
        },
    )

    # ── Conditional edge: after score + state update ──
    graph.add_conditional_edges(
        "update_state",
        route_after_score,
        {
            "continue": "generate_content",
            "reinforce": "generate_content",
            "check_mastery": "check_mastery",
            "session_end": END,
        },
    )

    # ── Conditional edge: after mastery check ──
    graph.add_conditional_edges(
        "check_mastery",
        route_after_mastery,
        {
            "upgrade": END,
            "continue": "generate_content",
            "session_end": END,
        },
    )

    # ── Error handler always terminates ──
    graph.add_edge("handle_error", END)

    logger.info("learning_session_graph_compiled")
    return graph.compile(checkpointer=checkpointer, interrupt_after=["deliver_to_tutor"])
