import uuid
from collections.abc import Generator

from fastapi import Depends
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


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_access_token(token)
    if user_id is None:
        raise CredentialsException()
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise CredentialsException()
    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise NotFoundException("User")
    return user
