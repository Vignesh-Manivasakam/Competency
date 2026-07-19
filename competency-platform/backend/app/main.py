"""Competency Intelligence Platform — Main FastAPI Application.

Spec reference: §9.1 FastAPI Router Structure (Listing 11).
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import PlatformError, platform_error_handler
from app.core.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    TenantResolutionMiddleware,
)

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
    app.state.redis = await init_redis()
    try:
        await init_neo4j()
        # Run constraint creation
        from app.core.neo4j import get_neo4j_session
        async with get_neo4j_session() as session:
            await session.run("CREATE CONSTRAINT competency_id_unique IF NOT EXISTS FOR (c:Competency) REQUIRE c.id IS UNIQUE")
            await session.run("CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE")
            await session.run("CREATE CONSTRAINT employee_id_unique IF NOT EXISTS FOR (e:Employee) REQUIRE e.id IS UNIQUE")
    except Exception as e:
        # Neo4j may not be available during initial dev or constraint creation failed
        import structlog
        logger = structlog.get_logger()
        logger.warning(f"Neo4j startup failed: {e} — running without graph DB")
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

# Register error handler
app.add_exception_handler(PlatformError, platform_error_handler)

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
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TenantResolutionMiddleware)

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
