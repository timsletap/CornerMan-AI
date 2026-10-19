import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StrikeType(str, enum.Enum):
    JAB = "jab"
    CROSS = "cross"
    HOOK = "hook"
    UPPERCUT = "uppercut"
    BODY_SHOT = "body_shot"
    ELBOW = "elbow"
    KNEE = "knee"
    KICK = "kick"
    OTHER = "other"


class Hand(str, enum.Enum):
    LEFT = "left"
    RIGHT = "right"


class StrikeEvent(Base):
    __tablename__ = "strike_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    timestamp_ms: Mapped[int] = mapped_column(Integer)
    frame_number: Mapped[int] = mapped_column(Integer)
    strike_type: Mapped[StrikeType] = mapped_column(Enum(StrikeType))
    hand: Mapped[Hand] = mapped_column(Enum(Hand))
    velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    keypoints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("AnalysisSession", back_populates="strike_events")
    error_flags = relationship("ErrorFlag", back_populates="strike_event", lazy="selectin")
