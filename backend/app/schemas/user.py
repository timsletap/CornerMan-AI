import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import ExperienceLevel, Stance, UserRole, UserTier, WeightClass


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    stance: Stance | None = None
    weight_class: WeightClass | None = None
    experience_level: ExperienceLevel | None = None

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v
    stance: Stance | None = None
    weight_class: WeightClass | None = None
    experience_level: ExperienceLevel | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    stance: Stance | None
    weight_class: WeightClass | None
    experience_level: ExperienceLevel | None
    tier: UserTier
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
