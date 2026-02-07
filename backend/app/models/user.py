import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Stance(str, enum.Enum):
    ORTHODOX = "orthodox"
    SOUTHPAW = "southpaw"
    SWITCH = "switch"


class WeightClass(str, enum.Enum):
    STRAWWEIGHT = "strawweight"
    FLYWEIGHT = "flyweight"
    BANTAMWEIGHT = "bantamweight"
    FEATHERWEIGHT = "featherweight"
    LIGHTWEIGHT = "lightweight"
    WELTERWEIGHT = "welterweight"
    MIDDLEWEIGHT = "middleweight"
    LIGHT_HEAVYWEIGHT = "light_heavyweight"
    HEAVYWEIGHT = "heavyweight"


class ExperienceLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    PRO = "pro"


class UserTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"


class UserRole(str, enum.Enum):
    FIGHTER = "fighter"
    COACH = "coach"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    stance: Mapped[Stance | None] = mapped_column(Enum(Stance), nullable=True)
    weight_class: Mapped[WeightClass | None] = mapped_column(
        Enum(WeightClass), nullable=True
    )
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        Enum(ExperienceLevel), nullable=True
    )
    tier: Mapped[UserTier] = mapped_column(Enum(UserTier), default=UserTier.FREE)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.FIGHTER)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    videos = relationship("Video", back_populates="user", lazy="selectin")
    analysis_sessions = relationship(
        "AnalysisSession", back_populates="user", lazy="selectin"
    )
    feedback_ratings = relationship(
        "FeedbackRating", back_populates="user", lazy="selectin"
    )
    usage_tracking = relationship(
        "UsageTracking", back_populates="user", lazy="selectin"
    )
