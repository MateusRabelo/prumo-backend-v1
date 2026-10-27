from datetime import datetime
from typing import Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    @field_validator('full_name', mode='before')
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    model_config = ConfigDict(str_strip_whitespace=False)

    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100, pattern=r".*\S.*")
    password: str = Field(..., min_length=10, max_length=128)


class UserLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    email: EmailStr
    password: str = Field(..., max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    current_family_id: Optional[UUID] = None


class PasswordChange(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    current_password: str
    new_password: str = Field(..., min_length=10, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    token: str
    new_password: str = Field(..., min_length=10, max_length=128)
