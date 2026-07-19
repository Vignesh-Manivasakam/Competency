# app/core/errors.py
from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse


class PlatformError(Exception):
    """Base exception for all platform errors."""
    def __init__(
        self,
        code: str,
        message: str,
        detail: str = "",
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        self.status_code = status_code


async def platform_error_handler(request: Request, exc: PlatformError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
                "request_id": getattr(request.state, "request_id", ""),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        },
    )


# --- Error Code Constants (§19.2) ---
class ErrorCodes:
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"          # 401
    PERMISSION_DENIED = "PERMISSION_DENIED"              # 403
    COMPETENCY_NOT_FOUND = "COMPETENCY_NOT_FOUND"        # 404
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"                  # 404
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"               # 404
    SESSION_ALREADY_ACTIVE = "SESSION_ALREADY_ACTIVE"     # 409
    PREREQUISITE_NOT_MET = "PREREQUISITE_NOT_MET"         # 409
    COMPETENCY_NOT_VALIDATED = "COMPETENCY_NOT_VALIDATED" # 409
    CYCLE_DETECTED_IN_GRAPH = "CYCLE_DETECTED_IN_GRAPH"  # 422
    DECOMPOSITION_IN_PROGRESS = "DECOMPOSITION_IN_PROGRESS"  # 409
    AGENT_TIMEOUT = "AGENT_TIMEOUT"                      # 503
    CONTENT_REVIEW_FAILED = "CONTENT_REVIEW_FAILED"      # 503
    INSUFFICIENT_ASSESSMENT_DATA = "INSUFFICIENT_ASSESSMENT_DATA"  # 422
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"          # 429
