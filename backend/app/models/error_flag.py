import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ErrorType(str, enum.Enum):
    DROPPED_GUARD = "dropped_guard"
    CHICKEN_WING = "chicken_wing"
    OTHER = "other"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ErrorFlag(Base):
    __tablename__ = "error_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    strike_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strike_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_type: Mapped[ErrorType] = mapped_column(Enum(ErrorType))
    timestamp_ms: Mapped[int] = mapped_column(Integer)
    frame_number: Mapped[int] = mapped_column(Integer)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.MEDIUM)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    user_disputed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("AnalysisSession", back_populates="error_flags")
    strike_event = relationship("StrikeEvent", back_populates="error_flags")
    drill_recommendations = relationship(
        "DrillRecommendation", back_populates="error_flag", lazy="selectin"
    )
