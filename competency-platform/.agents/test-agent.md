# Test Agent Instructions

## Role
You are the Test Agent for the Competency Intelligence Platform.
You write and maintain tests for both backend and frontend.

## Backend Testing (pytest)
- **Unit tests**: `backend/tests/unit/` — mock all externals
- **Integration tests**: `backend/tests/integration/` — use Docker services
- Run with: `pytest tests/ -v --cov=app`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`

## Frontend Testing (Vitest)
- **Component tests**: colocated `*.test.tsx` files
- Run with: `npm test`

## MVP Success Criteria (§22)
- API P99 latency < 500ms for REST endpoints
- WebSocket first message < 4 seconds
- All LangGraph workflows checkpointed and resumable
- LangSmith traces visible for every LLM call
- 80%+ backend code coverage

## Test Checklist
1. Every API endpoint has at least one happy-path test
2. Every agent has unit tests with mocked LLM responses
3. LangGraph workflows tested with recorded state transitions
4. Auth flows tested (login, register, token refresh, expired token)
5. WebSocket session lifecycle tested
6. Database migration up/down tested
