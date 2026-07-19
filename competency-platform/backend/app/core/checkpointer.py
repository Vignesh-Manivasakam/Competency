# app/core/checkpointer.py
"""LangGraph PostgreSQL checkpointer for persistent workflow state."""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import psycopg
from app.core.config import settings

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Get or create the LangGraph PostgreSQL checkpointer."""
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
