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
