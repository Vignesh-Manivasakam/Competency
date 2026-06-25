# Authentication & Security

## Plan 3 of 21 — Competency Intelligence Platform MVP

---

### Objective

Implement the complete authentication and authorization system: JWT token generation/validation (python-jose, HS256), password hashing (passlib + bcrypt), role-based access control (RBAC) middleware, all auth API endpoints, rate limiting, request logging, tenant resolution, and the standard error handling framework. After this plan, every API route can be protected with `Depends(get_current_user)` and role-gated with `Depends(require_role("manager"))`.

### Prerequisites

- **Plan 1** (Infrastructure Setup) — FastAPI scaffold, Redis running
- **Plan 2** (Database Schema) — User model with hashed_password field

### Spec References

| Section | Content |
|---------|---------|
| §8.2 Authentication Routes | POST /auth/token, /auth/register, /auth/refresh, GET /auth/me |
| §9.2 Middleware Stack | CORS, Rate Limiter, Request Logger, Tenant Resolution, Auth |
| §9.3 Dependency Injection Pattern | get_current_user, require_role, FastAPI dependencies |
| §19 Error Handling | PlatformError, standard error envelope, all error codes |
| §20 RBAC Permission Matrix | Admin/Manager/Employee permission grid |

---

### Files to Create/Modify

```
competency-platform/backend/app/
├── core/
│   ├── security.py          # JWT create/verify, password hash/verify
│   ├── middleware.py         # RateLimitMiddleware, RequestLoggingMiddleware, TenantResolutionMiddleware
│   └── errors.py            # PlatformError, exception handlers, error codes
├── api/
│   ├── dependencies.py      # get_current_user, require_role, get_async_session, get_redis
│   └── v1/
│       └── auth.py          # Auth router: /token, /register, /refresh, /me
├── schemas/
│   └── auth.py              # TokenResponse, UserCreate, LoginRequest Pydantic models
└── main.py                  # Update: register middleware + error handlers
```

---

### Detailed Implementation Steps

#### Step 1: Security Utilities (JWT + Password Hashing)

```python
# app/core/security.py
from datetime import datetime, timedelta
from typing import Any, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    role: str,
    tenant_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {
        "sub": subject,
        "role": role,
        "tenant_id": tenant_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_jwt(token: str) -> dict[str, Any]:
    """Decode and validate JWT. Raises JWTError on failure."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("sub") is None:
            raise JWTError("Missing subject")
        return payload
    except JWTError:
        raise
```

#### Step 2: Auth Pydantic Schemas

```python
# app/schemas/auth.py
from pydantic import BaseModel, Field, EmailStr, UUID4
from typing import Optional


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str
    role: str = Field(..., pattern="^(admin|manager|employee)$")
    job_title: Optional[str] = None
    department: Optional[str] = None


class UserOut(BaseModel):
    id: UUID4
    email: str
    full_name: str
    role: str
    job_title: Optional[str] = None
    department: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class RefreshRequest(BaseModel):
    refresh_token: str
```

#### Step 3: FastAPI Dependencies (from Listing 12 in Spec)

```python
# app/api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.db import get_async_session
from app.core.redis import get_redis
from app.core.security import verify_jwt
from app.models.user import User
from jose import JWTError

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Extract and validate JWT, return current user."""
    token = credentials.credentials
    try:
        payload = verify_jwt(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = await session.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return user


def require_role(*roles: str):
    """Dependency factory: restricts endpoint to specific roles."""
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user
    return checker
```

#### Step 4: Standard Error Handling Framework (from §19)

```python
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
```

#### Step 5: Middleware Stack (from §9.2)

```python
# app/core/middleware.py
import uuid
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from app.core.redis import get_redis_sync
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
```

#### Step 6: Auth Router

```python
# app/api/v1/auth.py
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.db import get_async_session
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, verify_jwt,
)
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import (
    LoginRequest, TokenResponse, UserCreate, UserOut, RefreshRequest,
)
from app.api.dependencies import get_current_user, require_role
from jose import JWTError

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Login; returns JWT access token."""
    result = await session.exec(select(User).where(User.email == data.email))
    user = result.first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        tenant_id=str(user.tenant_id),
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=UserOut)
async def register(
    data: UserCreate,
    admin: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_async_session),
):
    """Create new user account (admin only)."""
    # Check duplicate email
    existing = await session.exec(select(User).where(User.email == data.email))
    if existing.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        role=data.role,
        job_title=data.job_title,
        department=data.department,
        tenant_id=admin.tenant_id,  # Same tenant as admin
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Refresh expired token."""
    try:
        payload = verify_jwt(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await session.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        tenant_id=str(user.tenant_id),
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return user
```

#### Step 7: Update main.py with Middleware + Error Handlers

```python
# app/main.py — additions
from app.core.errors import PlatformError, platform_error_handler
from app.core.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    TenantResolutionMiddleware,
)

# Register error handler
app.add_exception_handler(PlatformError, platform_error_handler)

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
```

---

### RBAC Permission Matrix (from §20)

| Action | Admin | Manager | Employee |
|--------|-------|---------|----------|
| Create / delete users | ✓ | ✗ | ✗ |
| Create / edit competencies | ✓ | ✓ | ✗ |
| Trigger AI decomposition | ✓ | ✓ | ✗ |
| Validate skill graph | ✓ | ✓ | ✗ |
| Assign employees to competencies | ✓ | ✓ | ✗ |
| View team competency matrix | ✓ | ✓ (own team) | ✗ |
| Override mastery decisions | ✓ | ✓ | ✗ |
| View manager dashboard | ✓ | ✓ | ✗ |
| Start / resume own learning session | ✓ | ✓ | ✓ |
| View own learning state | ✓ | ✓ | ✓ |
| View own assessment history | ✓ | ✓ | ✓ |
| View own competency matrix | ✓ | ✓ | ✓ |
| Access LangSmith traces | ✓ | ✗ | ✗ |
| Configure system settings | ✓ | ✗ | ✗ |

---

### Error Code Reference (from §19.2)

| Code | HTTP | When Raised |
|------|------|-------------|
| INVALID_CREDENTIALS | 401 | JWT missing, expired, or bad signature |
| PERMISSION_DENIED | 403 | Insufficient role for operation |
| COMPETENCY_NOT_FOUND | 404 | competency_id does not exist |
| SKILL_NOT_FOUND | 404 | skill_id does not exist |
| SESSION_NOT_FOUND | 404 | session_id does not exist |
| SESSION_ALREADY_ACTIVE | 409 | Employee already has an active session for this skill |
| PREREQUISITE_NOT_MET | 409 | Prerequisite skills not mastered |
| COMPETENCY_NOT_VALIDATED | 409 | Skill graph not yet manager-approved |
| CYCLE_DETECTED_IN_GRAPH | 422 | Proposed edges would create a cycle in the DAG |
| DECOMPOSITION_IN_PROGRESS | 409 | AI decomposition already running |
| AGENT_TIMEOUT | 503 | LLM call timed out after max retries |
| CONTENT_REVIEW_FAILED | 503 | Content Reviewer rejected after 3 attempts |
| INSUFFICIENT_ASSESSMENT_DATA | 422 | Too few assessments for mastery decision |
| RATE_LIMIT_EXCEEDED | 429 | Exceeded 60 requests per minute |

---

### Configuration & Environment

```env
SECRET_KEY=your-jwt-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REDIS_URL=redis://localhost:6379/0
```

Dependencies:
```
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
structlog>=24.0
```

---

### Verification Criteria

1. **Registration**: POST /auth/register with admin token → creates user → returns UserOut
2. **Login**: POST /auth/token with valid credentials → returns access_token + refresh_token
3. **Protected route**: GET /auth/me with Bearer token → returns user profile
4. **Invalid token**: GET /auth/me with expired/bad token → 401
5. **RBAC**: Employee calling require_role("manager") endpoint → 403
6. **Rate limiting**: 61st request within 1 minute → 429
7. **Error envelope**: All errors return `{"error": {"code": ..., "message": ..., "detail": ..., "request_id": ..., "timestamp": ...}}`
8. **Refresh**: POST /auth/refresh with refresh_token → new access_token

### Notes & Gotchas

- **HS256 vs RS256**: Spec mentions RS256 in tech stack but HS256 in .env.example. Use HS256 for MVP simplicity; switch to RS256 for production
- **Token in WebSocket**: WebSocket auth uses `?token=` query param (not headers) — handled in Plan 15
- **Redis for rate limiting**: Redis must be injected into app state at startup via `app.state.redis`
- **Middleware order**: Starlette processes middleware in reverse registration order; CORS must be outermost
- **structlog**: Configure once in main.py startup event for JSON output
