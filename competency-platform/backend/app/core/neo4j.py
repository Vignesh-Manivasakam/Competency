# app/core/neo4j.py
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.core.config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator

_driver: AsyncDriver | None = None


async def init_neo4j() -> AsyncDriver:
    """Initialize the Neo4j async driver. Call once at app startup."""
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=50,
        connection_acquisition_timeout=30,
    )
    # Verify connectivity
    await _driver.verify_connectivity()
    return _driver


async def close_neo4j():
    """Close the Neo4j driver. Call at app shutdown."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


def get_neo4j_driver() -> AsyncDriver:
    """Get the initialized Neo4j driver instance."""
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_neo4j() first.")
    return _driver


@asynccontextmanager
async def get_neo4j_session() -> AsyncGenerator:
    """Async context manager for Neo4j sessions."""
    driver = get_neo4j_driver()
    async with driver.session(database="neo4j") as session:
        yield session
