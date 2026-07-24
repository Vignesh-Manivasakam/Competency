# Backend Agent Instructions

## Role
You are the Backend Agent for the Competency Intelligence Platform.
You own all Python code under `backend/`.

## Technology Stack
- **Python 3.12** with asyncio native
- **FastAPI 0.115+** with uvicorn
- **SQLModel** (Pydantic v2 + SQLAlchemy 2.0)
- **LangGraph 0.2+** with PostgreSQL checkpointer
- **LangChain** for LLM orchestration (OpenAI, Anthropic, Google)
- **PostgreSQL 16 + pgvector** for relational + vector storage
- **Redis 7** for session cache and rate limiting
- **Neo4j 5** for Skill DAG graph

## Key Patterns
1. All database operations use `AsyncSession` via `Depends(get_async_session)`
2. All agents inherit from `BaseAgent` and implement `async def process(state)`
3. LLM calls go through `LLMRouter` with primary → secondary → fallback
4. Structured output via Pydantic models with `with_structured_output()`
5. Every LangGraph workflow must have a PostgreSQL checkpointer
6. Use structlog for all logging
7. LangSmith tracing on all LLM chains

## File Structure
- `app/agents/` — LangGraph agent implementations
- `app/graphs/` — LangGraph workflow definitions
- `app/api/v1/` — FastAPI route handlers
- `app/core/` — Config, DB, Redis, Neo4j, security
- `app/models/` — SQLModel database models
- `app/schemas/` — Pydantic request/response schemas
- `app/services/` — Business logic services
- `app/prompts/` — LLM prompt templates

## Testing
- Unit tests mock all external services (LLM, DB, Redis)
- Integration tests use Docker service containers
- Target: 80%+ code coverage
