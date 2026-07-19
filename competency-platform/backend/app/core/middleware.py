# app/core/middleware.py
import uuid
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from app.core.security import verify_jwt
from jose import JWTError

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured JSON logging with trace IDs for every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.time()

        response = await call_next(request)

        process_time = time.time() - start_time
        logger.info(
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=round(process_time * 1000, 2),
        )
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """60 requests/min per user; 10 session creations/hr.
    Uses Redis counter with sliding window."""

    async def dispatch(self, request: Request, call_next):
        # Extract user from Authorization header if present
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = verify_jwt(token)
                user_id = payload.get("sub", "anonymous")
            except JWTError:
                user_id = "anonymous"
        else:
            user_id = "anonymous"

        # Skip rate limiting for anonymous (auth endpoints handle their own)
        if user_id != "anonymous":
            redis = request.app.state.redis
            key = f"rate:{user_id}:minute"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
            if count > 60:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Too many requests. Limit: 60/minute.",
                        }
                    },
                )

            # Session creation rate limit: 10/hr
            if request.url.path.endswith("/sessions") and request.method == "POST":
                session_key = f"rate:{user_id}:session_create"
                s_count = await redis.incr(session_key)
                if s_count == 1:
                    await redis.expire(session_key, 3600)
                if s_count > 10:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many session creations. Limit: 10/hour.",
                            }
                        },
                    )

        return await call_next(request)


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """Extracts tenant_id from JWT and injects into request state."""

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = verify_jwt(token)
                request.state.tenant_id = payload.get("tenant_id")
            except JWTError:
                request.state.tenant_id = None
        else:
            request.state.tenant_id = None

        return await call_next(request)
