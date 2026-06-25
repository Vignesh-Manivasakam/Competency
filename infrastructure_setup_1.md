# Infrastructure Setup

## Plan 1 of 21 — Competency Intelligence Platform MVP

---

### Objective

Bootstrap the entire development infrastructure for the Competency Intelligence Platform. This plan creates the Docker Compose stack (PostgreSQL 16 + pgvector, Redis 7, Neo4j 5 Community), the FastAPI application scaffold with uvicorn, the full backend directory structure, environment configuration, and the `pyproject.toml` with all project dependencies. After completing this plan, a developer can run `docker compose up` and hit a working health-check endpoint at `http://localhost:8000/docs`.

### Prerequisites

None — this is the foundational plan. All other plans depend on this one.

### Spec References

| Section | Lines | Content |
|---------|-------|---------|
| §2.2 Technology Stack | 370–434 | All technology choices and versions |
| §9.1 FastAPI Router Structure | 2278–2362 | `main.py` setup, middleware stack, router registration |
| §11 Project File Structure | 2682–2867 | Full backend + frontend directory tree |
| §12 Antigravity Setup | 2868–2962 | Dev environment config and task prompts |
| §16 Environment Config | 3251–3338 | `.env.example` and `docker-compose.yml` |

---

### Files to Create/Modify

```
competency-platform/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app + health check
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py            # Stub router
│   │   │       ├── competencies.py    # Stub router
│   │   │       ├── employees.py       # Stub router
│   │   │       ├── sessions.py        # Stub router
│   │   │       ├── websockets.py      # Stub router
│   │   │       ├── mastery.py         # Stub router
│   │   │       ├── assessments.py     # Stub router
│   │   │       ├── dashboard.py       # Stub router
│   │   │       └── dependencies.py    # Auth, DB, Redis deps (stub)
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── competency_architect.py
│   │   │   ├── learning_path_designer.py
│   │   │   ├── content_generator.py
│   │   │   ├── adaptive_tutor.py
│   │   │   ├── assessment_scoring.py
│   │   │   ├── mastery_evaluation.py
│   │   │   ├── learning_state_manager.py
│   │   │   ├── content_reviewer.py
│   │   │   └── orchestrator.py
│   │   ├── graphs/
│   │   │   ├── __init__.py
│   │   │   ├── competency_decomp.py
│   │   │   ├── baseline_assessment.py
│   │   │   ├── learning_session.py
│   │   │   ├── mastery_decision.py
│   │   │   └── state.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py              # pydantic-settings Settings
│   │   │   ├── db.py                  # AsyncSession factory
│   │   │   ├── redis.py              # Redis client
│   │   │   ├── neo4j.py              # Neo4j driver
│   │   │   ├── security.py           # JWT utilities (stub)
│   │   │   ├── middleware.py          # Custom middleware (stub)
│   │   │   └── embeddings.py         # pgvector operations (stub)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── competency.py
│   │   │   ├── session.py
│   │   │   ├── assessment.py
│   │   │   └── learning_state.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── competency.py
│   │   │   ├── session.py
│   │   │   ├── assessment.py
│   │   │   └── auth.py
│   │   ├── prompts/
│   │   │   ├── competency_architect.txt
│   │   │   ├── content_generator.txt
│   │   │   ├── adaptive_tutor.txt
│   │   │   ├── assessment_scoring.txt
│   │   │   └── mastery_evaluation.txt
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── langsmith.py
│   │       └── llm_router.py
│   ├── alembic/
│   │   └── (created by alembic init)
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── unit/
│   │   │   ├── __init__.py
│   │   │   ├── test_agents/
│   │   │   │   └── __init__.py
│   │   │   └── test_services/
│   │   │       └── __init__.py
│   │   └── integration/
│   │       ├── __init__.py
│   │       └── test_workflows/
│   │           └── __init__.py
│   ├── docker/
│   │   └── Dockerfile
│   ├── pyproject.toml
│   └── .env.example
├── docker-compose.yml
└── frontend/
    └── src/                           # (stub — created for structure only)
```

---

### Detailed Implementation Steps

#### Step 1: Create Root Project Directory and docker-compose.yml

Create the root `competency-platform/` directory and the Docker Compose file for the local development stack.

**File: `competency-platform/docker-compose.yml`**

```yaml
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: competency_db
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: redis-server --appendonly yes
    volumes: [redisdata:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/your-neo4j-password
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    ports: ["7474:7474", "7687:7687"]
    volumes: [neo4jdata:/data]
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p your-neo4j-password 'RETURN 1' || exit 1"]
      interval: 10s
      timeout: 10s
      retries: 5

  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:password@postgres:5432/competency_db
      DATABASE_URL_SYNC: postgresql://postgres:password@postgres:5432/competency_db
      REDIS_URL: redis://redis:6379/0
      NEO4J_URI: bolt://neo4j:7687
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    volumes: [./backend:/app]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  pgdata: {}
  redisdata: {}
  neo4jdata: {}
```

> [!IMPORTANT]
> The spec uses `pgvector/pgvector:pg16` — this is the official pgvector Docker image with PostgreSQL 16 and the vector extension pre-installed. Do NOT use the plain `postgres:16` image.

---

#### Step 2: Create Backend Dockerfile

**File: `competency-platform/backend/docker/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg (binary) and bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

Also create a root-level `backend/Dockerfile` that the docker-compose references:

**File: `competency-platform/backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

#### Step 3: Create pyproject.toml with All Dependencies

**File: `competency-platform/backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "competency-platform"
version = "1.0.0"
description = "Competency Intelligence Platform — AI-powered adaptive learning system"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.12"
dependencies = [
    # --- Web Framework ---
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",

    # --- ORM & Database ---
    "sqlmodel>=0.0.22",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "psycopg[binary]>=3.2.0",
    "pgvector>=0.3.0",
    "alembic>=1.14.0",

    # --- Auth & Security ---
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-multipart>=0.0.9",

    # --- LLM & Agents ---
    "langchain>=0.3.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-anthropic>=0.2.0",
    "langchain-google-genai>=2.0.0",
    "langgraph>=0.2.0",
    "langgraph-checkpoint-postgres>=2.0.0",

    # --- Observability ---
    "langsmith>=0.1.0",
    "structlog>=24.0.0",

    # --- Cache & Graph ---
    "redis[hiredis]>=5.0.0",
    "neo4j>=5.0.0",

    # --- Configuration ---
    "pydantic-settings>=2.5.0",

    # --- HTTP Client ---
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pre-commit>=3.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```

> [!NOTE]
> The spec specifies Python 3.12 with asyncio native, FastAPI 0.115+, SQLModel (Pydantic v2 + SQLAlchemy 2.0), and LangGraph 0.2+ with PostgreSQL checkpointer. All of these are captured above.

---

#### Step 4: Create .env.example

**File: `competency-platform/backend/.env.example`**

This is **verbatim from the spec** (§16, Listing 17):

```env
# ============================================
# Competency Intelligence Platform
# Environment Configuration
# ============================================

# Application
APP_ENV=development
SECRET_KEY=your-jwt-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/competency_db
DATABASE_URL_SYNC=postgresql://postgres:password@localhost:5432/competency_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# Default LLM routing
LLM_PRIMARY=gpt-4o                    # for complex reasoning
LLM_SECONDARY=gpt-4o-mini             # for content generation
LLM_FALLBACK=claude-sonnet-4-6        # when primary fails

# LangSmith (observability)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=competency-intelligence-mvp

# Embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Session config
MAX_SESSION_INTERACTIONS=25
SESSION_TIMEOUT_HOURS=24
MASTERY_CONFIDENCE_THRESHOLD=0.80
MIN_INTERACTIONS_FOR_MASTERY=3
```

---

#### Step 5: Create Core Config Module (pydantic-settings)

**File: `competency-platform/backend/app/core/config.py`**

```python
"""Application settings using pydantic-settings.

All values are loaded from environment variables or .env file.
Spec reference: §16 Environment Configuration.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — every env var in .env.example maps to a field here."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_ENV: str = "development"
    SECRET_KEY: str = "your-jwt-secret-key-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/competency_db"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://postgres:password@localhost:5432/competency_db"
    )

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Neo4j ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "your-neo4j-password"

    # --- LLM Providers ---
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    # --- LLM Routing ---
    LLM_PRIMARY: str = "gpt-4o"
    LLM_SECONDARY: str = "gpt-4o-mini"
    LLM_FALLBACK: str = "claude-sonnet-4-6"

    # --- LangSmith ---
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "competency-intelligence-mvp"

    # --- Embeddings ---
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # --- Session Config ---
    MAX_SESSION_INTERACTIONS: int = 25
    SESSION_TIMEOUT_HOURS: int = 24
    MASTERY_CONFIDENCE_THRESHOLD: float = 0.80
    MIN_INTERACTIONS_FOR_MASTERY: int = 3


# Singleton instance — import this everywhere
settings = Settings()
```

---

#### Step 6: Create Database Connection Module

**File: `competency-platform/backend/app/core/db.py`**

```python
"""Async database session factory.

Spec reference: §2.2 (SQLModel + asyncpg), §9.3 (Depends(get_async_session)).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# Create the async engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_ENV == "development"),
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

# Session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session.

    Usage in routes:
        session: AsyncSession = Depends(get_async_session)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

#### Step 7: Create Redis Client Module

**File: `competency-platform/backend/app/core/redis.py`**

```python
"""Redis client for session cache and rate limiting.

Spec reference: §2.2 (Redis 7, Upstash or self-hosted), §9.3 (Depends(get_redis)).
"""

from redis.asyncio import Redis

from app.core.config import settings

# Global Redis instance — initialized on app startup
_redis_client: Redis | None = None


async def init_redis() -> Redis:
    """Initialize the Redis connection pool. Called in app lifespan."""
    global _redis_client
    _redis_client = Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool. Called in app lifespan."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


async def get_redis() -> Redis:
    """FastAPI dependency that returns the Redis client.

    Usage in routes:
        redis = Depends(get_redis)
    """
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client
```

---

#### Step 8: Create Neo4j Driver Module

**File: `competency-platform/backend/app/core/neo4j.py`**

```python
"""Neo4j driver for the Skill DAG graph database.

Spec reference: §2.2 (Neo4j 5 Community, Skill DAG and dependencies).
"""

from neo4j import AsyncGraphDatabase, AsyncDriver

from app.core.config import settings

# Global driver — initialized on app startup
_neo4j_driver: AsyncDriver | None = None


async def init_neo4j() -> AsyncDriver:
    """Initialize the Neo4j async driver. Called in app lifespan."""
    global _neo4j_driver
    _neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    # Verify connectivity
    await _neo4j_driver.verify_connectivity()
    return _neo4j_driver


async def close_neo4j() -> None:
    """Close the Neo4j driver. Called in app lifespan."""
    global _neo4j_driver
    if _neo4j_driver:
        await _neo4j_driver.close()
        _neo4j_driver = None


async def get_neo4j_driver() -> AsyncDriver:
    """FastAPI dependency that returns the Neo4j driver."""
    if _neo4j_driver is None:
        raise RuntimeError("Neo4j not initialized. Call init_neo4j() first.")
    return _neo4j_driver
```

---

#### Step 9: Create Stub Modules for Security, Middleware, and Embeddings

**File: `competency-platform/backend/app/core/security.py`**

```python
"""JWT utilities — stub for Plan 3 (authentication_security_3.md).

Spec reference: §2.2 (python-jose + passlib, JWT RS256 + bcrypt).
"""

# Full implementation in Plan 3: authentication_security_3.md
```

**File: `competency-platform/backend/app/core/middleware.py`**

```python
"""Custom middleware — stub for Plan 3 (authentication_security_3.md).

Spec reference: §9.2 (CORS, Rate Limiter, Request Logger, Tenant Resolution).
"""

# Full implementation in Plan 3: authentication_security_3.md
```

**File: `competency-platform/backend/app/core/embeddings.py`**

```python
"""pgvector operations — stub for later implementation.

Spec reference: §18.1 RAG Pipeline Sub-Component.
"""

# Full implementation in a later plan
```

---

#### Step 10: Create All Stub API Routers

Each router file follows the same pattern. Create all of them under `app/api/v1/`.

**File: `competency-platform/backend/app/api/v1/__init__.py`**

```python
"""API v1 route package."""
```

**File: `competency-platform/backend/app/api/v1/auth.py`**

```python
"""Authentication routes — Login, register, refresh.

Spec reference: §8.2 Authentication Routes.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/token")
async def login():
    """Login; returns JWT access token."""
    # Implemented in Plan 3
    return {"message": "not implemented"}


@router.post("/register")
async def register():
    """Create new user account (admin only)."""
    return {"message": "not implemented"}


@router.post("/refresh")
async def refresh():
    """Refresh expired token."""
    return {"message": "not implemented"}


@router.get("/me")
async def get_me():
    """Get current user profile."""
    return {"message": "not implemented"}
```

**File: `competency-platform/backend/app/api/v1/competencies.py`**

```python
"""Competency CRUD + decompose + validate routes.

Spec reference: §8.3 Competency Routes.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/employees.py`**

```python
"""Employee management + assignment routes.

Spec reference: §8.4 Employee Routes.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/sessions.py`**

```python
"""Session lifecycle (REST) routes.

Spec reference: §8.5 Session Routes.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/websockets.py`**

```python
"""WebSocket session handler.

Spec reference: §8.5 WebSocket endpoint.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/mastery.py`**

```python
"""Mastery endpoints.

Spec reference: §8.6 Mastery Routes.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/assessments.py`**

```python
"""Assessment results endpoints.

Spec reference: §8.7 Assessment Routes.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/dashboard.py`**

```python
"""Manager dashboard endpoints.

Spec reference: §8.8 Dashboard Routes, §21.4 Dashboard Data Load Flow.
"""

from fastapi import APIRouter

router = APIRouter()
```

**File: `competency-platform/backend/app/api/v1/dependencies.py`**

```python
"""Core FastAPI dependencies — Auth, DB, Redis.

Spec reference: §9.3 Dependency Injection Pattern (Listing 12).
Stub — full implementation in Plan 3.
"""

# Full dependency implementations in Plan 3: authentication_security_3.md
```

---

#### Step 11: Create the Main FastAPI Application

**File: `competency-platform/backend/app/main.py`**

This is based on **Listing 11** from the spec (§9.1, lines 2281–2362):

```python
"""Competency Intelligence Platform — Main FastAPI Application.

Spec reference: §9.1 FastAPI Router Structure (Listing 11).
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    auth,
    competencies,
    employees,
    sessions,
    mastery,
    assessments,
    dashboard,
    websockets,
)
from app.core.config import settings
from app.core.db import engine
from app.core.redis import init_redis, close_redis
from app.core.neo4j import init_neo4j, close_neo4j


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown events."""
    # Startup
    await init_redis()
    try:
        await init_neo4j()
    except Exception:
        # Neo4j may not be available during initial dev
        import structlog
        logger = structlog.get_logger()
        logger.warning("Neo4j connection failed — running without graph DB")
    yield
    # Shutdown
    await close_redis()
    await close_neo4j()
    await engine.dispose()


app = FastAPI(
    title="Competency Intelligence Platform API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# -----------------------------------------------------------------
# Middleware stack (order matters: outer -> inner)
# -----------------------------------------------------------------
# Note: RateLimitMiddleware, RequestLoggingMiddleware, and
# TenantResolutionMiddleware are implemented in Plan 3.
# For now, only CORS is active.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------
# Route registration — Spec §9.1 Listing 11, lines 30-39
# -----------------------------------------------------------------
API_V1 = "/api/v1"

app.include_router(auth.router, prefix=f"{API_V1}/auth", tags=["auth"])
app.include_router(competencies.router, prefix=f"{API_V1}/competencies", tags=["competencies"])
app.include_router(employees.router, prefix=f"{API_V1}/employees", tags=["employees"])
app.include_router(sessions.router, prefix=f"{API_V1}/sessions", tags=["sessions"])
app.include_router(mastery.router, prefix=f"{API_V1}/mastery", tags=["mastery"])
app.include_router(assessments.router, prefix=f"{API_V1}/assessments", tags=["assessments"])
app.include_router(dashboard.router, prefix=f"{API_V1}/dashboard", tags=["dashboard"])
app.include_router(websockets.router, prefix=f"{API_V1}", tags=["websocket"])


# -----------------------------------------------------------------
# Health Check Endpoint
# -----------------------------------------------------------------
@app.get("/health", tags=["system"])
async def health_check():
    """Basic health check endpoint.

    Returns service status and environment info.
    Used by Docker healthcheck and monitoring.
    """
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "version": "1.0.0",
    }


@app.get("/", tags=["system"])
async def root():
    """Root endpoint — redirect to docs."""
    return {
        "message": "Competency Intelligence Platform API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
```

---

#### Step 12: Create All Stub Directories and `__init__.py` Files

Create empty `__init__.py` files for every Python package directory. This is critical for Python imports to work.

```python
# All __init__.py files contain:
"""Package marker."""
```

**Create the following `__init__.py` files:**

```
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/api/v1/__init__.py
backend/app/agents/__init__.py
backend/app/graphs/__init__.py
backend/app/core/__init__.py
backend/app/models/__init__.py
backend/app/schemas/__init__.py
backend/app/services/__init__.py
backend/tests/__init__.py
backend/tests/unit/__init__.py
backend/tests/unit/test_agents/__init__.py
backend/tests/unit/test_services/__init__.py
backend/tests/integration/__init__.py
backend/tests/integration/test_workflows/__init__.py
```

**Create stub agent files:**

```
backend/app/agents/base.py
backend/app/agents/competency_architect.py
backend/app/agents/learning_path_designer.py
backend/app/agents/content_generator.py
backend/app/agents/adaptive_tutor.py
backend/app/agents/assessment_scoring.py
backend/app/agents/mastery_evaluation.py
backend/app/agents/learning_state_manager.py
backend/app/agents/content_reviewer.py
backend/app/agents/orchestrator.py
```

Each stub agent file should contain:

```python
"""Agent stub — implemented in a later plan."""
```

**Create stub graph files:**

```
backend/app/graphs/competency_decomp.py
backend/app/graphs/baseline_assessment.py
backend/app/graphs/learning_session.py
backend/app/graphs/mastery_decision.py
backend/app/graphs/state.py
```

**Create stub model files:**

```
backend/app/models/user.py
backend/app/models/competency.py
backend/app/models/session.py
backend/app/models/assessment.py
backend/app/models/learning_state.py
```

**Create stub schema files:**

```
backend/app/schemas/competency.py
backend/app/schemas/session.py
backend/app/schemas/assessment.py
backend/app/schemas/auth.py
```

**Create empty prompt template files:**

```
backend/app/prompts/competency_architect.txt
backend/app/prompts/content_generator.txt
backend/app/prompts/adaptive_tutor.txt
backend/app/prompts/assessment_scoring.txt
backend/app/prompts/mastery_evaluation.txt
```

**Create stub service files:**

```
backend/app/services/langsmith.py
backend/app/services/llm_router.py
```

---

#### Step 13: Create Frontend Directory Stubs

Create the minimal frontend directory structure as defined in spec §11:

```
frontend/src/
├── pages/
│   ├── manager/
│   └── employee/
├── components/
│   ├── ui/
│   ├── dag/
│   ├── session/
│   ├── charts/
│   └── layout/
├── hooks/
├── api/
├── store/
└── public/
```

Each directory gets a `.gitkeep` file to ensure it's tracked in Git.

---

### Key Code Snippets from Spec

#### Listing 11: main.py and router registration (§9.1)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import (
    auth, competencies, employees, sessions,
    mastery, assessments, dashboard, websockets
)
from app.core.middleware import (
    RateLimitMiddleware, RequestLoggingMiddleware,
    TenantResolutionMiddleware
)

app = FastAPI(
    title="Competency Intelligence Platform API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Middleware stack (order matters: outer -> inner)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TenantResolutionMiddleware)

# Route registration
API_V1 = "/api/v1"
app.include_router(auth.router, prefix=f"{API_V1}/auth", tags=["auth"])
app.include_router(competencies.router, prefix=f"{API_V1}/competencies", tags=["competencies"])
app.include_router(employees.router, prefix=f"{API_V1}/employees", tags=["employees"])
app.include_router(sessions.router, prefix=f"{API_V1}/sessions", tags=["sessions"])
app.include_router(mastery.router, prefix=f"{API_V1}/mastery", tags=["mastery"])
app.include_router(assessments.router, prefix=f"{API_V1}/assessments", tags=["assessments"])
app.include_router(dashboard.router, prefix=f"{API_V1}/dashboard", tags=["dashboard"])
app.include_router(websockets.router, prefix=f"{API_V1}", tags=["websocket"])
```

#### Listing 18: docker-compose.yml (§16)

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: competency_db
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: redis-server --appendonly yes
    volumes: [redisdata:/data]
  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/your-neo4j-password
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    ports: ["7474:7474", "7687:7687"]
    volumes: [neo4jdata:/data]
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:password@postgres:5432/competency_db
      REDIS_URL: redis://redis:6379/0
      NEO4J_URI: bolt://neo4j:7687
    depends_on: [postgres, redis, neo4j]
    volumes: [./backend:/app]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
volumes:
  pgdata: {}
  redisdata: {}
  neo4jdata: {}
```

---

### Configuration & Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `development` | Controls debug logging, SQL echo |
| `SECRET_KEY` | (must change) | JWT signing key |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async DB connection |
| `DATABASE_URL_SYNC` | `postgresql://...` | Sync DB connection (Alembic) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt protocol |
| `OPENAI_API_KEY` | (required) | OpenAI API access |
| `LANGCHAIN_TRACING_V2` | `true` | Enable LangSmith tracing |

---

### Error Handling

Not applicable to this plan — error handling infrastructure is set up in Plan 3.

---

### Verification Criteria

- [ ] **Docker Compose starts cleanly**: `docker compose up -d` brings up all 4 services (postgres, redis, neo4j, backend) without errors
- [ ] **PostgreSQL is reachable**: `docker compose exec postgres psql -U postgres -c "SELECT 1"` returns successfully
- [ ] **pgvector extension is available**: `docker compose exec postgres psql -U postgres -d competency_db -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname = 'vector';"` returns a version
- [ ] **Redis is reachable**: `docker compose exec redis redis-cli ping` returns `PONG`
- [ ] **Neo4j is reachable**: Neo4j browser at `http://localhost:7474` loads successfully
- [ ] **FastAPI health check works**: `curl http://localhost:8000/health` returns `{"status": "healthy", ...}`
- [ ] **Swagger docs render**: `http://localhost:8000/docs` loads the interactive API documentation
- [ ] **OpenAPI schema available**: `curl http://localhost:8000/openapi.json` returns the schema JSON
- [ ] **All routers registered**: Swagger docs show all 8 tag groups (auth, competencies, employees, sessions, mastery, assessments, dashboard, websocket)
- [ ] **Local dev without Docker**: `cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload` starts the app on port 8000

---

### Notes & Gotchas

> [!WARNING]
> **pgvector image**: The spec explicitly requires `pgvector/pgvector:pg16`, NOT `postgres:16`. The standard PostgreSQL image does not include the vector extension. Using the wrong image will cause `CREATE EXTENSION vector` to fail.

> [!TIP]
> **Local development without Docker**: For faster iteration, run the FastAPI app directly with `uvicorn app.main:app --reload` while using Dockerized databases. The `.env` file defaults point to `localhost`, which works for this setup.

> [!NOTE]
> **Neo4j plugins**: The spec requests APOC and Graph Data Science plugins (`NEO4J_PLUGINS: '["apoc", "graph-data-science"]'`). The community edition includes APOC, but GDS may require additional setup. If GDS fails to load, it's acceptable to proceed without it for MVP.

> [!IMPORTANT]
> **Async everywhere**: The spec mandates Python 3.12 with asyncio native. All database operations use `asyncpg` through `SQLModel`'s async session. Never use synchronous database calls in request handlers — the only exception is Alembic migrations, which use `DATABASE_URL_SYNC`.

- **Middleware order matters**: CORSMiddleware must be outermost. The spec specifies outer→inner: CORS → RateLimit → RequestLogging → TenantResolution. Middleware stubs are created here; full implementation is in Plan 3.
- **The `lifespan` context manager** replaces the deprecated `@app.on_event("startup")`/`@app.on_event("shutdown")` pattern per modern FastAPI best practices.
- **Neo4j graceful degradation**: The lifespan catches Neo4j connection failures and logs a warning instead of crashing, since Neo4j may not be needed during initial development stages.
