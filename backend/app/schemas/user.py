import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import ExperienceLevel, Stance, UserRole, UserTier, WeightClass


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    stance: Stance | None = None
    weight_class: WeightClass | None = None
    experience_level: ExperienceLevel | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
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
