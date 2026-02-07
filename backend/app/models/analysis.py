import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("videos.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus), default=AnalysisStatus.QUEUED
    )
    total_strikes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    guard_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vision_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    coach_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="analysis_sessions")
    video = relationship("Video", back_populates="analysis_sessions")
    strike_events = relationship(
        "StrikeEvent", back_populates="session", lazy="selectin"
    )
    error_flags = relationship("ErrorFlag", back_populates="session", lazy="selectin")
    drill_recommendations = relationship(
        "DrillRecommendation", back_populates="session", lazy="selectin"
    )
    feedback_ratings = relationship(
        "FeedbackRating", back_populates="session", lazy="selectin"
    )
