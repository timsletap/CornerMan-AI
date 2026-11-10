import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.analysis import AnalysisStatus
from app.models.error_flag import ErrorType, Severity
from app.models.feedback import Rating
from app.models.strike import Hand, HandRole, StrikeType


class StrikeEventResponse(BaseModel):
    id: uuid.UUID
    timestamp_ms: int
    frame_number: int
    strike_type: StrikeType
    hand: Hand
    hand_role: HandRole | None = None
    onset_ms: int | None = None
    velocity: float | None
    keypoints: dict[str, Any] | None

    model_config = {"from_attributes": True}


class ErrorFlagResponse(BaseModel):
    id: uuid.UUID
    strike_event_id: uuid.UUID | None
    error_type: ErrorType
    timestamp_ms: int
    frame_number: int
    severity: Severity
    details: dict[str, Any] | None
    measured_value_sw: float | None = None
    window_start_ms: int | None = None
    window_end_ms: int | None = None
    user_disputed: bool

    model_config = {"from_attributes": True}


class DrillResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    error_type: str
    difficulty_level: int
    video_url: str | None

    model_config = {"from_attributes": True}


class DrillRecommendationResponse(BaseModel):
    id: uuid.UUID
    drill: DrillResponse
    priority: int

    model_config = {"from_attributes": True}


class AnalysisSessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    video_id: uuid.UUID
    status: AnalysisStatus
    total_strikes: int | None
    avg_velocity: float | None
    guard_score: float | None
    coach_feedback: str | None
    annotated_video_path: str | None
    target_track_id: int | None = None
    stance_used: str | None = None
    stance_source: str | None = None
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisSessionDetailResponse(AnalysisSessionResponse):
    vision_json: dict[str, Any] | None = None
    strike_events: list[StrikeEventResponse] = []
    error_flags: list[ErrorFlagResponse] = []
    drill_recommendations: list[DrillRecommendationResponse] = []


class AnalyzeRequest(BaseModel):
    """Optional body for POST /videos/{id}/analyze."""

    target_track_id: int | None = Field(
        default=None, description="Tracker id of the fighter to analyze, from a previous run"
    )
    stance_override: Literal["orthodox", "southpaw"] | None = Field(
        default=None, description="Stance to classify with, instead of the profile's"
    )


class FeedbackCreateRequest(BaseModel):
    rating: Rating
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    rating: Rating
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DisputeRequest(BaseModel):
    error_flag_id: uuid.UUID


class ProgressResponse(BaseModel):
    step: str
    progress: float
    detail: str
