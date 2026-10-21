"""Shared fixtures for API tests that don't need a real database.

Auth and DB dependencies are overridden; tests that exercise DB queries belong in the
Postgres-backed suite (QA-03).
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.main import app


def _fake_refresh(obj: Any) -> None:
    # Mimic the columns Postgres fills on insert.
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()
    if getattr(obj, "created_at", None) is None:
        obj.created_at = datetime.now(UTC)


@pytest.fixture
def fake_db() -> MagicMock:
    db = MagicMock()
    db.refresh.side_effect = _fake_refresh
    return db


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "uploads"
    monkeypatch.setattr(settings, "VIDEO_UPLOAD_DIR", str(path))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    return path


@pytest.fixture
def client(fake_db: MagicMock) -> Iterator[TestClient]:
    user = SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        yield TestClient(app)  # no context manager: skip the drill-seeding lifespan
    finally:
        app.dependency_overrides.clear()
