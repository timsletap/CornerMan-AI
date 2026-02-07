import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, NotFoundException
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
)
from app.schemas.common import MessageResponse

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
    video = (
        db.query(Video)
        .filter(Video.id == video_id, Video.user_id == current_user.id)
        .first()
    )
    if not video:
        raise NotFoundException("Video")

    # TODO: Check usage quota via services
    # TODO: Dispatch Celery task

    session = AnalysisSession(
        user_id=current_user.id,
        video_id=video.id,
        status=AnalysisStatus.QUEUED,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
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
