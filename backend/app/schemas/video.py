import uuid
from datetime import datetime

from pydantic import BaseModel

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
    start_time: float
    end_time: float
