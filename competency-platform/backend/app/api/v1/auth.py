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
