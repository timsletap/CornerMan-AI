"""Video service - local/S3 storage, ffprobe validation, and path resolution."""

import os
import tempfile
import uuid
from pathlib import Path

import boto3
import ffmpeg
from fastapi import UploadFile

from app.config import settings


def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def generate_s3_key(user_id: uuid.UUID, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    return f"videos/{user_id}/{uuid.uuid4()}.{ext}"


UPLOAD_CHUNK_BYTES = 1024 * 1024


class UploadTooLargeError(Exception):
    """Raised when an upload stream exceeds the size limit."""


async def stream_upload_to_temp(file: UploadFile, max_bytes: int, suffix: str) -> tuple[Path, int]:
    """Copy an upload to a temp file under VIDEO_UPLOAD_DIR in 1 MB chunks.

    Args:
        file: the incoming upload.
        max_bytes: size limit in bytes; exceeding it deletes the temp file and raises
            UploadTooLargeError.
        suffix: file extension for the temp file, e.g. ".mp4".

    Returns (temp_path, size_in_bytes). The temp file lives on the same filesystem as
    the final location so store_video can rename it atomically.
    """
    tmp_dir = Path(settings.VIDEO_UPLOAD_DIR) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=tmp_dir, suffix=f"{suffix}.part")
    temp_path = Path(name)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLargeError(f"upload exceeds {max_bytes} bytes")
                out.write(chunk)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path, size


def store_video(temp_path: Path, user_id: uuid.UUID, filename: str) -> tuple[str, str]:
    """Move a validated temp file into storage. Returns (key, url/path).

    Local storage uses an atomic rename; S3 uploads from disk and removes the temp file.
    """
    key = generate_s3_key(user_id, filename)
    if settings.STORAGE_BACKEND == "local":
        full_path = Path(settings.VIDEO_UPLOAD_DIR) / key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, full_path)
        return key, str(full_path.resolve())

    ext = key.rsplit(".", 1)[-1]
    content_type = "video/mp4" if ext == "mp4" else "video/quicktime"
    try:
        _get_s3_client().upload_file(
            str(temp_path),
            settings.S3_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": content_type},
        )
    finally:
        temp_path.unlink(missing_ok=True)
    s3_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    return key, s3_url


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


def download_from_s3(s3_key: str) -> str:
    """Download a file from S3 to a temp file. Returns the temp file path."""
    s3 = _get_s3_client()
    ext = s3_key.rsplit(".", 1)[-1] if "." in s3_key else "mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
    s3.download_fileobj(settings.S3_BUCKET_NAME, s3_key, tmp)
    tmp.close()
    return tmp.name


def get_video_path(video) -> str:
    """Resolve the absolute filesystem path for a Video record."""
    if settings.STORAGE_BACKEND == "local":
        return str(Path(settings.VIDEO_UPLOAD_DIR).resolve() / video.s3_key)
    else:
        return download_from_s3(video.s3_key)


def delete_video_file(file_path_or_key: str) -> None:
    """Delete a video file from local storage or S3."""
    if settings.STORAGE_BACKEND == "local":
        try:
            os.remove(file_path_or_key)
        except OSError:
            pass
    else:
        try:
            s3 = _get_s3_client()
            s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_path_or_key)
        except Exception:
            pass
