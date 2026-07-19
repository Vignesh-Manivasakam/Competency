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
