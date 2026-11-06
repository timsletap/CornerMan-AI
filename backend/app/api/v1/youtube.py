"""YouTube scraping endpoints for UFC fight clips."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.schemas.video import VideoResponse
from app.services.video import delete_video_file, validate_video_file
from app.services.youtube import download_youtube_clip, search_youtube_clips

router = APIRouter(prefix="/youtube", tags=["YouTube"])


class YouTubeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be blank")
        return v


class YouTubeSearchResult(BaseModel):
    url: str
    title: str
    duration: int | None
    thumbnail: str | None
    channel: str


class YouTubeDownloadRequest(BaseModel):
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def _valid_http_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("url must be a valid http(s) URL")
        return v


@router.post("/search", response_model=list[YouTubeSearchResult])
def search_clips(
    payload: YouTubeSearchRequest,
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    results = search_youtube_clips(payload.query, payload.max_results)
    return results


@router.post("/download", response_model=VideoResponse, status_code=201)
def download_clip(
    payload: YouTubeDownloadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Video:
    try:
        result = download_youtube_clip(payload.url, current_user.id)
    except ValueError as e:
        raise BadRequestException(str(e)) from e
    except Exception as e:
        raise BadRequestException(f"Download failed: {str(e)}") from e

    # Same content check as uploads: must be a real video within the duration limit
    validation = validate_video_file(result["path"], result["filename"])
    if not validation["valid"]:
        delete_video_file(result["path"])
        raise BadRequestException(validation.get("error", "Invalid video file"))

    video = Video(
        user_id=current_user.id,
        original_filename=result["filename"],
        s3_key=result["s3_key"],
        s3_url=result["path"],
        file_size_bytes=result["file_size_bytes"],
        duration_seconds=validation.get("duration_seconds", result["duration"]),
        format="mp4",
        status=VideoStatus.VALIDATED,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video
