import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_from_token_or_query, get_db
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


@router.get("/sessions/{session_id}/annotated-stream")
def stream_annotated_video(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user_from_token_or_query),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Stream the annotated video with skeleton overlay."""
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

    # Clean up annotated video file if it exists
    if session.annotated_video_path:
        p = Path(session.annotated_video_path)
        if p.exists():
            p.unlink(missing_ok=True)

    # Use raw SQL DELETE so DB-level ON DELETE CASCADE handles children
    db.execute(
        text("DELETE FROM analysis_sessions WHERE id = :sid"),
        {"sid": str(session_id)},
    )
    db.commit()


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
        .filter(
            ErrorFlag.id == payload.error_flag_id,
            ErrorFlag.session_id == session_id,
        )
        .first()
    )
    if not error_flag:
        raise NotFoundException("Error flag")
    error_flag.user_disputed = True
    db.commit()
    return {"message": "Error flag marked as disputed"}
