# LangGraph Setup & Orchestrator

## Plan 5 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the core agent orchestration layer: the `BaseAgent` abstract class, `AgentState` TypedDict, LangGraph orchestrator supervisor (managing 4 workflow graphs), PostgreSQL checkpointer for state persistence, the LLM Router for multi-model routing, and LangSmith tracing integration. After this plan, any agent can be built by extending `BaseAgent`, and all LangGraph workflows have persistent state that survives crashes.

### Prerequisites

- **Plan 1** (Infrastructure) — PostgreSQL running, FastAPI scaffold
- **Plan 2** (Database Schema) — Database tables migrated
- **Plan 3** (Auth & Security) — Error handling framework

### Spec References

| Section | Content |
|---------|---------|
| §3 Orchestrator Agent | Central coordinator, workflow graphs, state machine |
| §4.1 Core LangGraph State Definition | AgentState TypedDict (Listing 1) |
| §4.2 Learning Session Graph | Full graph code (Listing 2) |
| §5.3 PostgreSQL Checkpointer | AsyncPostgresSaver setup (Listing 3) |
| §17 Observability with LangSmith | Tracing configuration (Listing 19) |
| §18.2 LLM Router | Model selection logic (Listing 21) |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── agents/
│   ├── __init__.py
│   ├── base.py                    # BaseAgent abstract class
│   └── orchestrator.py            # LangGraph supervisor coordinator
├── graphs/
│   ├── __init__.py
│   ├── state.py                   # AgentState TypedDict
│   ├── competency_decomp.py       # Decomposition workflow graph
│   ├── baseline_assessment.py     # Baseline assessment graph
│   ├── learning_session.py        # Main session workflow graph
│   └── mastery_decision.py        # Mastery decision graph
├── services/
│   ├── llm_router.py              # Multi-model routing
│   └── langsmith.py               # LangSmith tracing config
└── core/
    └── checkpointer.py            # PostgreSQL checkpointer setup
```

---

### Detailed Implementation Steps

#### Step 1: AgentState TypedDict (from §4.1 Listing 1)

```python
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
```

#### Step 2: PostgreSQL Checkpointer (from §5.3 Listing 3)

```python
# app/core/checkpointer.py
"""LangGraph PostgreSQL checkpointer for persistent workflow state."""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import psycopg
from app.core.config import settings

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Get or create the LangGraph PostgreSQL checkpointer.
    
    From spec §5.3 Listing 3:
    Enables:
    - Resume any interrupted session from the exact graph node that failed
    - Full audit trail of every agent state transition
    - Time-travel debugging (inspect any past state snapshot)
    """
    global _checkpointer
    if _checkpointer is None:
        conn = await psycopg.AsyncConnection.connect(
            settings.DATABASE_URL_SYNC,  # psycopg uses sync-style URL
            autocommit=True,
        )
        _checkpointer = AsyncPostgresSaver(conn)
        await _checkpointer.setup()  # creates langgraph tables if not exist
    return _checkpointer


async def close_checkpointer():
    """Close the checkpointer connection."""
    global _checkpointer
    if _checkpointer is not None:
        _checkpointer = None
```

#### Step 3: LLM Router (from §18.2 Listing 21)

```python
# app/services/llm_router.py
"""LLM model selection and routing per agent."""
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from app.core.config import settings

# Agent-to-model mapping from spec §18.2
AGENT_MODEL_MAP = {
    "CompetencyArchitectAgent": "gpt-4o",
    "LearningPathDesignerAgent": "gpt-4o-mini",
    "ContentGeneratorAgent": "gpt-4o-mini",
    "AdaptiveTutorAgent": "gpt-4o",
    "AssessmentScoringAgent": "gpt-4o",
    "MasteryEvaluationAgent": "gpt-4o",
    "ContentReviewerAgent": "gpt-4o-mini",
}

# Content-type specific overrides for Content Generator
CONTENT_TYPE_MODEL_MAP = {
    "explanation": "gpt-4o-mini",
    "quiz": "gpt-4o-mini",
    "scenario": "gpt-4o",
    "dialogue": "gpt-4o",
}


def get_llm(agent_name: str, temperature: float = 0.3):
    """Get the appropriate LLM for an agent.
    
    Primary: OpenAI (model from AGENT_MODEL_MAP)
    Fallback: Anthropic Claude Sonnet 4.6
    """
    model = AGENT_MODEL_MAP.get(agent_name, "gpt-4o-mini")
    try:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            timeout=30,
            max_retries=2,
        )
    except Exception:
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            temperature=temperature,
            timeout=30,
        )


def get_llm_structured(agent_name: str, schema: type):
    """Get LLM configured for structured (JSON schema) output.
    
    Used by agents that need typed responses:
    - CompetencyArchitectAgent (skill decomposition)
    - AssessmentScoringAgent (dimension scores)
    - MasteryEvaluationAgent (mastery decisions)
    """
    llm = get_llm(agent_name, temperature=0.1)
    return llm.with_structured_output(schema, method="json_schema")


def get_llm_for_content(content_type: str, temperature: float = 0.7):
    """Get model based on content type (Content Generator specific)."""
    model = CONTENT_TYPE_MODEL_MAP.get(content_type, "gpt-4o-mini")
    try:
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            timeout=30,
            max_retries=2,
        )
    except Exception:
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            temperature=temperature,
            timeout=30,
        )
```

#### Step 4: LangSmith Tracing Integration (from §17 Listing 19)

```python
# app/services/langsmith.py
"""LangSmith observability configuration for all agent invocations."""
from langsmith import Client
from langchain_core.callbacks import LangChainTracer
from langchain_core.runnables import RunnableConfig
from app.core.config import settings


def get_runnable_config(session_id: str, agent_name: str) -> RunnableConfig:
    """Standard runnable config for all agent invocations.
    
    From spec §17 Listing 19:
    Provides per-agent dashboards showing:
    - Token usage
    - Latency percentiles
    - Success rates
    - Full prompt/response trace for every invocation
    """
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
```

#### Step 5: BaseAgent Abstract Class

```python
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
    """Abstract base class for all MVP agents.
    
    Every agent follows the standard contract from §3:
    - Typed input, typed output
    - Defined tools
    - Memory scope
    - Prompt strategy
    - Failure handling
    """

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
        """Process the agent state and return updates.
        
        Each agent implements this with its specific logic.
        Returns a dict of state updates to merge into AgentState.
        """
        ...

    async def __call__(self, state: AgentState) -> dict:
        """LangGraph node invocation wrapper with error handling.
        
        From spec §3 (Orchestrator):
        Each node has a try/except wrapper. Failures route to
        error-handling sub-graph with exponential backoff (1s, 2s, 4s)
        then fallback or human escalation.
        """
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
```

#### Step 6: Orchestrator Agent

```python
# app/agents/orchestrator.py
"""Central orchestrator — manages all LangGraph workflow graphs.

From spec §3 (Orchestrator Agent):
Role: Central coordinator. Receives all system events, determines
which agents to invoke in which order, manages workflow state,
and handles failures.

Workflow Graphs:
- competency_decomposition_graph
- baseline_assessment_graph
- learning_session_graph
- mastery_decision_graph
"""
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
        """Execute a workflow graph with checkpointing.
        
        Args:
            workflow_type: One of 'decomposition', 'baseline', 'learning', 'mastery'
            initial_state: Initial AgentState dict
            thread_id: Unique ID for checkpointing (usually session_id)
        
        Returns:
            Final state after graph execution
        """
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
        """Resume a checkpointed workflow from where it left off.
        
        Enables: Resume any interrupted session from the exact
        graph node that failed.
        """
        graph = self.get_graph(workflow_type)
        config = {"configurable": {"thread_id": thread_id}}

        if updates:
            final_state = await graph.ainvoke(updates, config=config)
        else:
            # Get the last checkpoint and continue
            state = await graph.aget_state(config)
            final_state = await graph.ainvoke(None, config=config)

        return final_state


# Global orchestrator instance
orchestrator = Orchestrator()
```

#### Step 7: Graph Stub Files (Detailed in Plans 7, 15)

```python
# app/graphs/competency_decomp.py
"""Competency decomposition workflow — stub. Full impl in Plan 7."""
from langgraph.graph import StateGraph, END
from app.graphs.state import AgentState


def build_competency_decomp_graph(checkpointer):
    graph = StateGraph(AgentState)
    # Nodes added in Plan 7
    graph.add_node("placeholder", lambda state: state)
    graph.set_entry_point("placeholder")
    graph.add_edge("placeholder", END)
    return graph.compile(checkpointer=checkpointer)


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
```

#### Step 8: Error Handler Node

```python
# app/graphs/error_handler.py
"""Error handling node for all LangGraph workflows."""
import structlog
from app.graphs.state import AgentState

logger = structlog.get_logger()


async def handle_error(state: AgentState) -> dict:
    """Error handling sub-graph node.
    
    From spec §3 (Orchestrator):
    Failures route to error-handling sub-graph with
    exponential backoff (1s, 2s, 4s) then fallback
    or human escalation.
    """
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
```

---

### Configuration & Environment

```env
# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# Default LLM routing
LLM_PRIMARY=gpt-4o
LLM_SECONDARY=gpt-4o-mini
LLM_FALLBACK=claude-sonnet-4-6

# LangSmith (observability)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=competency-intelligence-mvp

# Database (for checkpointer)
DATABASE_URL_SYNC=postgresql://postgres:password@localhost:5432/competency_db
```

Dependencies:
```
langgraph>=0.2
langgraph-checkpoint-postgres>=0.1
langchain-core>=0.3
langchain-openai>=0.2
langchain-anthropic>=0.2
langchain-google-genai>=2.0
langsmith>=0.1
psycopg[binary]>=3.1
```

---

### Verification Criteria

1. **Checkpointer creates tables**: After `get_checkpointer()`, LangGraph checkpoint tables exist in PostgreSQL
2. **LLM Router works**: `get_llm("CompetencyArchitectAgent")` returns ChatOpenAI(model="gpt-4o")
3. **LLM Router fallback**: If OpenAI unavailable, `get_llm()` returns ChatAnthropic
4. **Structured output**: `get_llm_structured("AssessmentScoringAgent", DimensionScores)` returns model with JSON output
5. **BaseAgent can be subclassed**: Create a test agent extending BaseAgent → `__call__()` works with error handling
6. **Orchestrator initializes**: `orchestrator.initialize()` compiles all 4 workflow graphs
7. **Workflow execution**: `orchestrator.run_workflow("decomposition", state, thread_id)` runs placeholder graph
8. **Checkpointing works**: Run a workflow → kill it → `resume_workflow()` picks up from last node
9. **LangSmith traces**: After running an agent, traces appear in LangSmith dashboard
10. **Error handling**: Agent raising exception → retry with backoff → fallback after 3 retries

### Notes & Gotchas

- **psycopg vs asyncpg**: The LangGraph checkpointer uses `psycopg` (not `asyncpg`). Both are needed in the project
- **Checkpointer tables**: `AsyncPostgresSaver.setup()` creates `checkpoints` and `checkpoint_writes` tables automatically
- **Thread ID**: Use `session_id` as the thread_id for learning workflows, and `f"decomp-{competency_id}"` for decomposition
- **Graph stubs**: Stubs compile successfully but just pass through — they're replaced in Plans 7, 14, 15
- **LangSmith free tier**: Sufficient for MVP — full trace visibility without cost
- **Temperature settings**: Evaluation agents (Assessment, Mastery) use temperature=0.1; creative agents (Content Generator) use 0.7
