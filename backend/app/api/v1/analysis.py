import json
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_media_signature
from app.config import settings
from app.core.exceptions import NotFoundException, QuotaExceededException
from app.models.analysis import AnalysisSession, AnalysisStatus
from app.models.error_flag import ErrorFlag
from app.models.feedback import FeedbackRating
from app.models.user import User
from app.models.video import Video
from app.schemas.analysis import (
    AnalysisSessionDetailResponse,
    AnalysisSessionResponse,
    DisputeRequest,
    FeedbackCreateRequest,
    FeedbackResponse,
    ProgressResponse,
)
from app.schemas.common import MessageResponse
from app.services.cleanup import local_video_path, remove_files, session_files
from app.services.progress import get_progress
from app.services.usage import check_api_credit_quota, check_upload_quota, increment_upload_count
from app.tasks.analysis_tasks import run_analysis_pipeline

router = APIRouter(tags=["Analysis"])


@router.post(
    "/videos/{video_id}/analyze",
    response_model=AnalysisSessionResponse,
    status_code=202,
)
def trigger_analysis(
    video_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisSession:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if not video:
        raise NotFoundException("Video")

    if not check_upload_quota(db, current_user):
        raise QuotaExceededException("Daily upload limit reached")
    if not check_api_credit_quota(db, current_user):
        raise QuotaExceededException("API credit limit reached")

    increment_upload_count(db, current_user.id)

    session = AnalysisSession(
        user_id=current_user.id,
        video_id=video.id,
        status=AnalysisStatus.QUEUED,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    run_analysis_pipeline.delay(str(session.id), str(video.id))

    return session


@router.get("/sessions", response_model=list[AnalysisSessionResponse])
def list_sessions(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisSession]:
    return (
        db.query(AnalysisSession)
        .filter(AnalysisSession.user_id == current_user.id)
        .order_by(AnalysisSession.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/sessions/{session_id}", response_model=AnalysisSessionDetailResponse)
def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisSession:
    session = (
        db.query(AnalysisSession)
        .filter(
            AnalysisSession.id == session_id,
            AnalysisSession.user_id == current_user.id,
        )
        .first()
    )
    if not session:
        raise NotFoundException("Analysis session")
    return session


@router.get("/sessions/{session_id}/progress", response_model=ProgressResponse)
def get_analysis_progress(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Get real-time progress for an in-progress analysis."""
    session = (
        db.query(AnalysisSession)
        .filter(
            AnalysisSession.id == session_id,
            AnalysisSession.user_id == current_user.id,
        )
        .first()
    )
    if not session:
        raise NotFoundException("Analysis session")

    if session.status == AnalysisStatus.COMPLETED:
        return {"step": "complete", "progress": 1.0, "detail": "Analysis complete!"}
    if session.status == AnalysisStatus.FAILED:
        return {"step": "failed", "progress": 0.0, "detail": "Analysis failed."}

    progress = get_progress(str(session_id))
    if progress:
        return progress
    return {"step": "queued", "progress": 0.0, "detail": "Waiting in queue..."}


# How often the event stream re-checks progress and status, and when it sends a
# keepalive comment so proxies don't drop an idle connection (seconds).
EVENTS_POLL_SECONDS = 0.5
EVENTS_KEEPALIVE_SECONDS = 15.0
EVENTS_MAX_SECONDS = 3600.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _progress_payload(progress: dict) -> dict:
    return {
        "stage": progress.get("step", "queued"),
        "pct": progress.get("progress", 0.0),
        "message": progress.get("detail", ""),
    }


def _session_events(session_id: uuid.UUID, db: Session) -> Iterator[str]:
    """Yield SSE frames until the session completes or fails (PLT-07).

    The DB status is the source of truth for the terminal event; Redis holds the
    in-flight stage written by the worker.
    """
    sid = str(session_id)
    last: dict | None = None
    last_sent = started = time.monotonic()
    try:
        while time.monotonic() - started < EVENTS_MAX_SECONDS:
            status = (
                db.query(AnalysisSession.status).filter(AnalysisSession.id == session_id).scalar()
            )
            db.close()  # end the transaction so the next check sees new commits
            if status is None or status == AnalysisStatus.FAILED:
                progress = get_progress(sid) or {}
                yield _sse("failed", {"message": progress.get("detail") or "Analysis failed."})
                return
            if status == AnalysisStatus.COMPLETED:
                yield _sse(
                    "done", {"stage": "complete", "pct": 1.0, "message": "Analysis complete!"}
                )
                return

            payload = _progress_payload(get_progress(sid) or {"detail": "Waiting in queue..."})
            now = time.monotonic()
            if payload != last:
                yield _sse("progress", payload)
                last, last_sent = payload, now
            elif now - last_sent >= EVENTS_KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                last_sent = now
            time.sleep(EVENTS_POLL_SECONDS)
    finally:
        db.close()


@router.get(
    "/sessions/{session_id}/events",
    dependencies=[Depends(require_media_signature("events", "session_id"))],
)
def stream_session_events(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Server-sent progress events: `progress` (stage, pct, message), then `done` or
    `failed`, after which the stream closes. Auth is a signed URL (EventSource can't
    send headers)."""
    return StreamingResponse(
        _session_events(session_id, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/sessions/{session_id}/annotated-stream",
    dependencies=[Depends(require_media_signature("annotated", "session_id"))],
)
def stream_annotated_video(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Stream the annotated video with skeleton overlay. Auth is a signed URL."""
    session = db.query(AnalysisSession).filter(AnalysisSession.id == session_id).first()
    if not session:
        raise NotFoundException("Analysis session")
    if not session.annotated_video_path:
        raise NotFoundException("Annotated video")
    if not Path(session.annotated_video_path).exists():
        raise NotFoundException("Annotated video file")

    return FileResponse(
        session.annotated_video_path,
        media_type="video/mp4",
        filename=f"cornerman_analysis_{session_id}.mp4",
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete an analysis session and all related data."""
    session = (
        db.query(AnalysisSession)
        .filter(
            AnalysisSession.id == session_id,
            AnalysisSession.user_id == current_user.id,
        )
        .first()
    )
    if not session:
        raise NotFoundException("Analysis session")

    video = db.query(Video).filter(Video.id == session.video_id).first()
    video_dir = (
        local_video_path(video).parent
        if video is not None and settings.STORAGE_BACKEND == "local"
        else None
    )
    paths = session_files(session, video_dir)

    # Bulk DELETE so Postgres ON DELETE CASCADE removes strikes, flags, drills, feedback
    db.query(AnalysisSession).filter(AnalysisSession.id == session_id).delete(
        synchronize_session=False
    )
    db.commit()

    remove_files(paths, f"session {session_id}")


@router.post("/sessions/{session_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    session_id: uuid.UUID,
    payload: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackRating:
    session = (
        db.query(AnalysisSession)
        .filter(
            AnalysisSession.id == session_id,
            AnalysisSession.user_id == current_user.id,
        )
        .first()
    )
    if not session:
        raise NotFoundException("Analysis session")
    feedback = FeedbackRating(
        session_id=session.id,
        user_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@router.post("/sessions/{session_id}/dispute", response_model=MessageResponse)
def dispute_error(
    session_id: uuid.UUID,
    payload: DisputeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    error_flag = (
        db.query(ErrorFlag)
        .join(AnalysisSession, AnalysisSession.id == ErrorFlag.session_id)
        .filter(
            ErrorFlag.id == payload.error_flag_id,
            ErrorFlag.session_id == session_id,
            AnalysisSession.user_id == current_user.id,
        )
        .first()
    )
    if not error_flag:
        raise NotFoundException("Error flag")
    error_flag.user_disputed = True
    db.commit()
    return {"message": "Error flag marked as disputed"}
