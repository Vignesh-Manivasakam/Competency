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
