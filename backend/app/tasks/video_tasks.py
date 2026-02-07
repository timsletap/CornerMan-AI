"""Celery tasks for video validation and compression."""

from app.tasks.celery_app import celery_app


@celery_app.task(name="tasks.validate_video")
def validate_video(video_id: str) -> dict:
    """Validate uploaded video file format and integrity.

    TODO: Implement - download from S3, run ffprobe, update status.
    """
    return {"video_id": video_id, "status": "validated"}


@celery_app.task(name="tasks.compress_video")
def compress_video(video_id: str) -> dict:
    """Compress video for processing efficiency.

    TODO: Implement - download, compress with ffmpeg, re-upload.
    """
    return {"video_id": video_id, "status": "compressed"}
