# app/agents/orchestrator.py
"""Central orchestrator — manages all LangGraph workflow graphs."""
import structlog
from app.core.checkpointer import get_checkpointer

logger = structlog.get_logger()


class Orchestrator:
    """Manages compiled LangGraph workflow graphs."""

    def __init__(self):
        self._graphs = {}

    async def initialize(self):
        """Compile all workflow graphs with checkpointer."""
        checkpointer = await get_checkpointer()

        # Import graph builders (each defined in their own plan)
        from app.graphs.competency_decomp import build_competency_decomp_graph
        from app.graphs.baseline_assessment import build_baseline_assessment_graph
        from app.graphs.learning_session import build_learning_session_graph
        from app.graphs.mastery_decision import build_mastery_decision_graph

        self._graphs["decomposition"] = build_competency_decomp_graph(checkpointer)
        self._graphs["baseline"] = build_baseline_assessment_graph(checkpointer)
        self._graphs["learning"] = build_learning_session_graph(checkpointer)
        self._graphs["mastery"] = build_mastery_decision_graph(checkpointer)

        logger.info("orchestrator_initialized", graphs=list(self._graphs.keys()))

    def get_graph(self, workflow_type: str):
        """Get a compiled graph by workflow type."""
        if workflow_type not in self._graphs:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        return self._graphs[workflow_type]

    async def run_workflow(
        self,
        workflow_type: str,
        initial_state: dict,
        thread_id: str,
    ) -> dict:
        """Execute a workflow graph with checkpointing."""
        graph = self.get_graph(workflow_type)
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(
            "workflow_started",
            workflow_type=workflow_type,
            thread_id=thread_id,
        )

        final_state = await graph.ainvoke(initial_state, config=config)

        logger.info(
            "workflow_completed",
            workflow_type=workflow_type,
            thread_id=thread_id,
            final_node=final_state.get("current_node"),
            error=final_state.get("error"),
        )

        return final_state

    async def resume_workflow(
        self,
        workflow_type: str,
        thread_id: str,
        updates: dict | None = None,
    ) -> dict:
        """Resume a checkpointed workflow from where it left off."""
        graph = self.get_graph(workflow_type)
        config = {"configurable": {"thread_id": thread_id}}

        if updates:
            final_state = await graph.ainvoke(updates, config=config)
        else:
            # Continue from the last checkpoint
            final_state = await graph.ainvoke(None, config=config)

        return final_state


# Global orchestrator instance
orchestrator = Orchestrator()
