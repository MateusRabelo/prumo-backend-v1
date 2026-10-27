from datetime import datetime
from typing import Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, EmailStr, Field


class FamilyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    currency: str = Field(default="BRL", max_length=10)


class FamilyResponse(BaseModel):
    role: Optional[str] = None
    members_count: int = 1
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner_id: UUID
    currency: str
    created_at: datetime


class FamilyMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    user_id: UUID
    role: str
    alias_name: str
    joined_at: datetime
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


class FamilyInviteCreate(BaseModel):
    invited_email: EmailStr
    role: str = Field(default="MEMBER", pattern="^(ADMIN|MEMBER)$")


class FamilyInviteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    invited_email: EmailStr
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class FamilyInviteResponse(FamilyInviteSummary):
    token: str


class FamilyInviteAccept(BaseModel):
    token: str
    alias_name: Optional[str] = None
