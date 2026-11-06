import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.video import VideoStatus


class VideoUploadResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_size_bytes: int
    format: str
    status: VideoStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    s3_url: str | None
    file_size_bytes: int
    duration_seconds: float | None
    format: str
    trim_start: float | None
    trim_end: float | None
    status: VideoStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoTrimRequest(BaseModel):
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered_times(self) -> "VideoTrimRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self
