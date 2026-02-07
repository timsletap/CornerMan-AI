import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.schemas.video import VideoResponse, VideoTrimRequest, VideoUploadResponse
from app.services.video import delete_video_file, save_video, validate_video_file

router = APIRouter(prefix="/videos", tags=["Videos"])

ALLOWED_FORMATS = {"mp4", "mov"}


@router.post("/upload", response_model=VideoUploadResponse, status_code=201)
async def upload_video(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Video:
    if not file.filename:
        raise BadRequestException("No filename provided")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_FORMATS:
        raise BadRequestException(f"Invalid format. Allowed: {ALLOWED_FORMATS}")

    content = await file.read()
    file_size = len(content)
    max_bytes = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise BadRequestException(f"File exceeds {settings.MAX_VIDEO_SIZE_MB}MB limit")

    # Save file to storage
    s3_key, file_url = save_video(content, current_user.id, file.filename)

    # Validate video integrity and duration
    validation = validate_video_file(file_url, file.filename)
    if not validation["valid"]:
        delete_video_file(file_url)
        raise BadRequestException(validation.get("error", "Invalid video file"))

    video = Video(
        user_id=current_user.id,
        original_filename=file.filename,
        s3_key=s3_key,
        s3_url=file_url,
        file_size_bytes=file_size,
        duration_seconds=validation.get("duration_seconds"),
        format=ext,
        status=VideoStatus.VALIDATED,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


@router.get("/", response_model=list[VideoResponse])
def list_videos(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Video]:
    return (
        db.query(Video)
        .filter(Video.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Video:
    video = (
        db.query(Video)
        .filter(Video.id == video_id, Video.user_id == current_user.id)
        .first()
    )
    if not video:
        raise NotFoundException("Video")
    return video


@router.patch("/{video_id}/trim", response_model=VideoResponse)
def trim_video(
    video_id: uuid.UUID,
    payload: VideoTrimRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Video:
    video = (
        db.query(Video)
        .filter(Video.id == video_id, Video.user_id == current_user.id)
        .first()
    )
    if not video:
        raise NotFoundException("Video")
    if payload.end_time - payload.start_time > settings.MAX_VIDEO_DURATION_SECONDS:
        raise BadRequestException(
            f"Trimmed duration exceeds {settings.MAX_VIDEO_DURATION_SECONDS}s limit"
        )
    video.trim_start = payload.start_time
    video.trim_end = payload.end_time
    db.commit()
    db.refresh(video)
    return video


@router.delete("/{video_id}", status_code=204)
def delete_video(
    video_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    video = (
        db.query(Video)
        .filter(Video.id == video_id, Video.user_id == current_user.id)
        .first()
    )
    if not video:
        raise NotFoundException("Video")
    if video.s3_url:
        delete_video_file(video.s3_url)
    db.delete(video)
    db.commit()
