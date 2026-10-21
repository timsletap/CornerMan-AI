"""Signed media URLs (PLT-03).

<video src> can't send an Authorization header, so the frontend asks this endpoint for
a short-lived signed URL instead of putting the JWT in the query string.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core import media_signing
from app.core.exceptions import NotFoundException
from app.core.media_signing import MediaResourceType
from app.models.analysis import AnalysisSession
from app.models.user import User
from app.models.video import Video

router = APIRouter(prefix="/media", tags=["Media"])

STREAM_PATHS: dict[str, str] = {
    "video": "/api/v1/videos/{id}/stream",
    "annotated": "/api/v1/sessions/{id}/annotated-stream",
}


class SignRequest(BaseModel):
    resource_type: MediaResourceType
    resource_id: uuid.UUID


class SignResponse(BaseModel):
    url: str
    """Path relative to the API base URL, including exp and sig query params."""
    expires_at: datetime


def _owns(db: Session, user: User, resource_type: str, resource_id: uuid.UUID) -> bool:
    model = Video if resource_type == "video" else AnalysisSession
    query = db.query(model.id).filter(model.id == resource_id, model.user_id == user.id)
    return query.first() is not None


@router.post("/sign", response_model=SignResponse)
def sign_media_url(
    payload: SignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SignResponse:
    if not _owns(db, current_user, payload.resource_type, payload.resource_id):
        raise NotFoundException("Resource")
    exp = media_signing.new_expiry()
    sig = media_signing.sign(payload.resource_type, payload.resource_id, exp)
    path = STREAM_PATHS[payload.resource_type].format(id=payload.resource_id)
    return SignResponse(
        url=f"{path}?exp={exp}&sig={sig}",
        expires_at=datetime.fromtimestamp(exp, tz=UTC),
    )
