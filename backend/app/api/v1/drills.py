import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.analysis import AnalysisSession
from app.models.drill import Drill, DrillRecommendation
from app.models.user import User
from app.schemas.analysis import DrillRecommendationResponse, DrillResponse

router = APIRouter(prefix="/drills", tags=["Drills"])


@router.get("/", response_model=list[DrillResponse])
def list_drills(
    error_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[Drill]:
    query = db.query(Drill)
    if error_type:
        query = query.filter(Drill.error_type == error_type)
    return query.all()


@router.get(
    "/sessions/{session_id}/recommendations",
    response_model=list[DrillRecommendationResponse],
)
def get_recommendations(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DrillRecommendation]:
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
    return (
        db.query(DrillRecommendation)
        .filter(DrillRecommendation.session_id == session_id)
        .order_by(DrillRecommendation.priority)
        .all()
    )
