"""Postgres-backed fixtures for tests that need real queries and ON DELETE CASCADE.

Set TEST_DATABASE_URL (default postgresql://cornerman:cornerman@localhost:5432/cornerman_test).
The schema is dropped and rebuilt with `alembic upgrade head`, so the database name
must end in `_test`. Tests are skipped when the database is unreachable.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import Base
from app.main import app
from app.models.analysis import AnalysisSession, AnalysisStatus
from app.models.error_flag import ErrorFlag, ErrorType
from app.models.feedback import FeedbackRating, Rating
from app.models.strike import Hand, StrikeEvent, StrikeType
from app.models.user import User
from app.models.video import Video, VideoStatus

BACKEND = Path(__file__).resolve().parents[2] / "backend"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://cornerman:cornerman@localhost:5432/cornerman_test"
)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    url = make_url(TEST_DATABASE_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail(f"refusing to reset non-test database {url.database!r}")
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip(f"test database not reachable at {url.render_as_string()}")

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    with mock.patch.object(settings, "DATABASE_URL", url.render_as_string(hide_password=False)):
        command.upgrade(cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=db_engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with db_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_client(db_engine: Engine) -> Iterator[TestClient]:
    """App client using the test database and real JWT auth."""
    make_session = sessionmaker(bind=db_engine, autoflush=False)

    def override_get_db() -> Iterator[Session]:
        session = make_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)  # no context manager: skip the drill-seeding lifespan
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session) -> Callable[[str], tuple[User, dict[str, str]]]:
    """Create a user; returns (user, auth headers)."""

    def factory(email: str | None = None) -> tuple[User, dict[str, str]]:
        user = User(
            email=email or f"{uuid.uuid4().hex[:8]}@example.test",
            password_hash=hash_password("correct horse battery staple"),
            full_name="Test Fighter",
        )
        db.add(user)
        db.commit()
        return user, {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    return factory


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "uploads"
    monkeypatch.setattr(settings, "VIDEO_UPLOAD_DIR", str(path))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    return path


@dataclass
class Seeded:
    video: Video
    sessions: list[AnalysisSession]
    files: list[Path] = field(default_factory=list)
    flag_ids: list[uuid.UUID] = field(default_factory=list)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"data")
    return path


@pytest.fixture
def seed_video(db: Session, upload_dir: Path) -> Callable[..., Seeded]:
    """Factory: a video on disk with analysed sessions (one strike, error flag, and
    feedback each), plus the leftover files the pipeline can produce."""

    def factory(user: User, n_sessions: int = 2) -> Seeded:
        vid = uuid.uuid4()
        key = f"videos/{user.id}/{vid}.mp4"
        original = _touch(upload_dir / key)
        video = Video(
            id=vid,
            user_id=user.id,
            original_filename="spar.mp4",
            s3_key=key,
            s3_url=str(original.resolve()),
            file_size_bytes=4,
            format="mp4",
            status=VideoStatus.COMPLETED,
        )
        db.add(video)
        seeded = Seeded(video=video, sessions=[], files=[original])
        seeded.files.append(_touch(original.with_name(f"{vid}_raw.mp4")))  # YouTube leftover

        for _ in range(n_sessions):
            sid = uuid.uuid4()
            annotated = _touch(original.with_name(f"{sid}_annotated.mp4"))
            seeded.files += [annotated, _touch(original.with_name(f"{sid}_annotated_h264.mp4"))]
            session = AnalysisSession(
                id=sid,
                user_id=user.id,
                video_id=vid,
                status=AnalysisStatus.COMPLETED,
                annotated_video_path=str(annotated.resolve()),
            )
            db.add(session)
            db.flush()
            strike = StrikeEvent(
                session_id=sid,
                timestamp_ms=1000,
                frame_number=30,
                strike_type=StrikeType.JAB,
                hand=Hand.LEFT,
            )
            db.add(strike)
            db.flush()
            flag = ErrorFlag(
                session_id=sid,
                strike_event_id=strike.id,
                error_type=ErrorType.DROPPED_GUARD,
                timestamp_ms=1000,
                frame_number=30,
            )
            db.add(flag)
            db.add(FeedbackRating(session_id=sid, user_id=user.id, rating=Rating.THUMBS_UP))
            db.flush()
            seeded.flag_ids.append(flag.id)
            seeded.sessions.append(session)
        db.commit()
        return seeded

    return factory
