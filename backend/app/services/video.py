"""Video service - local/S3 storage, ffprobe validation, and path resolution."""

import os
import uuid
from pathlib import Path

import ffmpeg

from app.config import settings


def generate_s3_key(user_id: uuid.UUID, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    return f"videos/{user_id}/{uuid.uuid4()}.{ext}"


def save_video_locally(
    file_content: bytes, user_id: uuid.UUID, filename: str
) -> tuple[str, str]:
    """Save video to local filesystem. Returns (relative_key, absolute_path)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    relative_key = f"videos/{user_id}/{uuid.uuid4()}.{ext}"

    upload_dir = Path(settings.VIDEO_UPLOAD_DIR)
    full_path = upload_dir / relative_key
    full_path.parent.mkdir(parents=True, exist_ok=True)

    full_path.write_bytes(file_content)
    return relative_key, str(full_path.resolve())


def save_video(
    file_content: bytes, user_id: uuid.UUID, filename: str
) -> tuple[str, str]:
    """Dispatch to local or S3 storage based on config. Returns (key, url/path)."""
    if settings.STORAGE_BACKEND == "local":
        return save_video_locally(file_content, user_id, filename)
    else:
        s3_key = generate_s3_key(user_id, filename)
        s3_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        return s3_key, s3_url


def validate_video_file(file_path: str, filename: str) -> dict:
    """Validate video file using ffprobe. Returns metadata dict with 'valid' key."""
    try:
        probe = ffmpeg.probe(file_path)
    except ffmpeg.Error:
        return {"valid": False, "error": "Cannot read video file", "duration_seconds": None}

    video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    if not video_streams:
        return {"valid": False, "error": "No video stream found", "duration_seconds": None}

    duration = float(probe["format"].get("duration", 0))
    if duration > settings.MAX_VIDEO_DURATION_SECONDS:
        return {
            "valid": False,
            "error": f"Duration {duration:.1f}s exceeds {settings.MAX_VIDEO_DURATION_SECONDS}s limit",
            "duration_seconds": duration,
        }

    vs = video_streams[0]
    fps_str = vs.get("r_frame_rate", "30/1")
    fps_parts = fps_str.split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0

    return {
        "valid": True,
        "duration_seconds": duration,
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "fps": fps,
        "codec": vs.get("codec_name", "unknown"),
    }


def get_video_path(video) -> str:
    """Resolve the absolute filesystem path for a Video record."""
    if settings.STORAGE_BACKEND == "local":
        return str(Path(settings.VIDEO_UPLOAD_DIR).resolve() / video.s3_key)
    else:
        raise NotImplementedError("S3 download not yet implemented")


def delete_video_file(file_path: str) -> None:
    """Delete a video file from local storage."""
    try:
        os.remove(file_path)
    except OSError:
        pass
