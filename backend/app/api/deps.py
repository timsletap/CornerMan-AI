import uuid
from collections.abc import Generator

from fastapi import Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import CredentialsException, NotFoundException
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


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user(token, db)


def get_current_user_from_token_or_query(
    request: Request,
    token: str | None = Query(None),
    db: Session = Depends(get_db),
) -> User:
    """Accept token from either Authorization header or ?token= query param.
    Used for endpoints called directly by <video src=...> tags."""
    # Try query param first
    if token:
        return _resolve_user(token, db)
    # Fall back to Authorization header
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return _resolve_user(auth[7:], db)
    raise CredentialsException()
