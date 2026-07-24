"""Shared test fixtures for the Competency Intelligence Platform.

From spec §15.2 (Listing 16):
Mock LLM pattern ensures deterministic agent testing without real API calls.

Fixtures provided:
- mock_llm: Creates a mock LLM returning predetermined JSON responses
- test_db_session: Mock AsyncSession for database operations
- test_redis: Fakeredis instance for cache tests
- test_client: httpx AsyncClient wired to the FastAPI app
- sample_agent_state: Prefilled AgentState for workflow tests
"""
import json
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from langchain_core.messages import AIMessage

from app.main import app
from app.core.db import get_async_session
from app.core.redis import get_redis


# ---------------------------------------------------------------------------
# §15.2 Mock LLM Factory (Listing 16)
# ---------------------------------------------------------------------------

def create_mock_llm(response_content: dict | str) -> AsyncMock:
    """Create a mock LLM that returns a predetermined response."""
    content = (
        json.dumps(response_content)
        if isinstance(response_content, dict)
        else response_content
    )

    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value=AIMessage(content=content))
    mock.invoke = MagicMock(return_value=AIMessage(content=content))

    structured_mock = AsyncMock()
    structured_mock.ainvoke = AsyncMock(return_value=response_content)
    mock.with_structured_output = MagicMock(return_value=structured_mock)

    return mock


def create_mock_structured_llm(response_obj: Any) -> AsyncMock:
    """Create a mock structured LLM that returns a Pydantic model instance."""
    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value=response_obj)
    return mock


# ---------------------------------------------------------------------------
# Test Database Session Mock
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_db_session():
    """Mock AsyncSession for isolated fast API unit/integration tests."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.refresh = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]), first=MagicMock(return_value=None)))
    mock_session.execute.return_value = mock_result
    yield mock_session


# ---------------------------------------------------------------------------
# Test Redis (fakeredis for cache tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_redis():
    """Fake Redis client for testing cache operations."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.hset = AsyncMock(return_value=1)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hgetall = AsyncMock(return_value={})
    return mock_redis


# ---------------------------------------------------------------------------
# Test HTTP Client (httpx AsyncClient for API tests)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_client(test_db_session, test_redis):
    """httpx AsyncClient wired to the FastAPI app with mock DB & Redis overrides."""
    async def override_get_session():
        yield test_db_session

    async def override_get_redis():
        yield test_redis

    app.dependency_overrides[get_async_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample AgentState for workflow tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_agent_state() -> dict:
    """Prefilled AgentState matching the TypedDict from §4.1 (Listing 1)."""
    return {
        "session_id": "test-session-001",
        "employee_id": "emp-001",
        "skill_id": "skill-python-basics",
        "competency_id": "comp-backend-eng",
        "workflow_type": "learning",
        "current_node": "start",
        "next_action": "",
        "messages": [],
        "current_proficiency": 0.5,
        "interaction_count": 0,
        "session_scores": [],
        "generated_content": {},
        "assessment_results": {},
        "mastery_decision": {},
        "error_count": 0,
        "max_interactions": 25,
    }


# ---------------------------------------------------------------------------
# Mock Neo4j Driver
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_neo4j():
    """Mock Neo4j driver for skill graph tests."""
    mock_driver = AsyncMock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = MagicMock(return_value=[])
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_driver.session = MagicMock(return_value=mock_session)
    return mock_driver
