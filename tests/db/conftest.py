"""Postgres-backed fixtures for tests that need real queries and ON DELETE CASCADE.

Set TEST_DATABASE_URL (default postgresql://cornerman:cornerman@localhost:5432/cornerman_test).
The schema is dropped and rebuilt with `alembic upgrade head`, so the database name
must end in `_test`. Tests are skipped when the database is unreachable.
"""

import os
import uuid
from collections.abc import Callable, Iterator
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
from app.models.user import User

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
