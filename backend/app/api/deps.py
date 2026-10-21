import uuid
from collections.abc import Callable, Generator

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import media_signing
from app.core.exceptions import CredentialsException, ForbiddenException, NotFoundException
from app.core.media_signing import MediaResourceType
from app.core.security import decode_access_token
from app.database import SessionLocal
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_user(token: str, db: Session) -> User:
    user_id = decode_access_token(token)
    if user_id is None:
        raise CredentialsException()
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise CredentialsException() from None
    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise NotFoundException("User")
    return user


def require_media_signature(resource_type: MediaResourceType, id_param: str) -> Callable[..., None]:
    """Dependency factory: the request must carry a valid ``exp``/``sig`` for the path id.

    Used by endpoints loaded directly by <video src>, which cannot send headers.
    Ownership is checked when the URL is signed (POST /media/sign).
    """

    def dependency(request: Request, exp: int | None = None, sig: str | None = None) -> None:
        try:
            resource_id = uuid.UUID(request.path_params[id_param])
        except (KeyError, ValueError):
            resource_id = None
        if (
            resource_id is None
            or exp is None
            or sig is None
            or not media_signing.verify(resource_type, resource_id, exp, sig)
        ):
            raise ForbiddenException("Invalid or expired media URL")

    return dependency


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user(token, db)
