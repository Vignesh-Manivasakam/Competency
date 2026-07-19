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
