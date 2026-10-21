"""PLT-03: signed media URLs replace ?token= on stream endpoints."""

import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core import media_signing

VIDEO_BYTES = bytes(range(256)) * 40


@pytest.fixture
def stored_video(upload_dir: Path, fake_db: MagicMock) -> SimpleNamespace:
    """A video row (returned by any DB query) whose file exists on disk."""
    key = "videos/u/clip.mp4"
    (upload_dir / "videos" / "u").mkdir(parents=True)
    (upload_dir / key).write_bytes(VIDEO_BYTES)
    video = SimpleNamespace(id=uuid.uuid4(), s3_key=key, format="mp4", original_filename="clip.mp4")
    fake_db.query.return_value.filter.return_value.first.return_value = video
    return video


def stream_url(video_id: uuid.UUID | str, exp: int, sig: str) -> str:
    return f"/api/v1/videos/{video_id}/stream?exp={exp}&sig={sig}"


def fresh(video_id: uuid.UUID, ttl: int = 60) -> tuple[int, str]:
    exp = int(time.time()) + ttl
    return exp, media_signing.sign("video", video_id, exp)


def test_valid_signature_streams(client: TestClient, stored_video: SimpleNamespace) -> None:
    exp, sig = fresh(stored_video.id)
    res = client.get(stream_url(stored_video.id, exp, sig))
    assert res.status_code == 200
    assert res.content == VIDEO_BYTES


def test_range_requests_still_supported(client: TestClient, stored_video: SimpleNamespace) -> None:
    exp, sig = fresh(stored_video.id)
    res = client.get(stream_url(stored_video.id, exp, sig), headers={"Range": "bytes=0-99"})
    assert res.status_code == 206
    assert res.content == VIDEO_BYTES[:100]


def test_expired_signature_403(client: TestClient, stored_video: SimpleNamespace) -> None:
    exp = int(time.time()) - 1
    sig = media_signing.sign("video", stored_video.id, exp)
    assert client.get(stream_url(stored_video.id, exp, sig)).status_code == 403


def test_tampered_id_403(client: TestClient, stored_video: SimpleNamespace) -> None:
    exp, sig = fresh(stored_video.id)
    assert client.get(stream_url(uuid.uuid4(), exp, sig)).status_code == 403


def test_tampered_exp_403(client: TestClient, stored_video: SimpleNamespace) -> None:
    exp, sig = fresh(stored_video.id)
    assert client.get(stream_url(stored_video.id, exp + 3600, sig)).status_code == 403


def test_signature_for_other_resource_type_403(
    client: TestClient, stored_video: SimpleNamespace
) -> None:
    exp = int(time.time()) + 60
    sig = media_signing.sign("annotated", stored_video.id, exp)
    assert client.get(stream_url(stored_video.id, exp, sig)).status_code == 403


@pytest.mark.parametrize("query", ["", "?exp=9999999999", "?sig=abc", "?token=some.jwt.token"])
def test_missing_signature_or_legacy_token_403(
    client: TestClient, stored_video: SimpleNamespace, query: str
) -> None:
    assert client.get(f"/api/v1/videos/{stored_video.id}/stream{query}").status_code == 403


def test_annotated_stream_requires_signature(client: TestClient, fake_db: MagicMock) -> None:
    sid = uuid.uuid4()
    assert client.get(f"/api/v1/sessions/{sid}/annotated-stream").status_code == 403


def test_sign_returns_working_url(client: TestClient, stored_video: SimpleNamespace) -> None:
    res = client.post(
        "/api/v1/media/sign",
        json={"resource_type": "video", "resource_id": str(stored_video.id)},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["url"].startswith(f"/api/v1/videos/{stored_video.id}/stream?exp=")
    assert "token" not in body["url"]
    assert client.get(body["url"]).status_code == 200


def test_sign_annotated_url_path(client: TestClient, stored_video: SimpleNamespace) -> None:
    sid = uuid.uuid4()
    res = client.post(
        "/api/v1/media/sign", json={"resource_type": "annotated", "resource_id": str(sid)}
    )
    assert res.json()["url"].startswith(f"/api/v1/sessions/{sid}/annotated-stream?exp=")


def test_user_cannot_sign_someone_elses_resource(client: TestClient, fake_db: MagicMock) -> None:
    # The ownership query filters by the current user; another user's resource finds nothing.
    fake_db.query.return_value.filter.return_value.first.return_value = None
    res = client.post(
        "/api/v1/media/sign",
        json={"resource_type": "video", "resource_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


def test_sign_requires_auth(fake_db: MagicMock) -> None:
    from app.main import app

    res = TestClient(app).post(
        "/api/v1/media/sign",
        json={"resource_type": "video", "resource_id": str(uuid.uuid4())},
    )
    assert res.status_code == 401


def test_sign_rejects_unknown_resource_type(client: TestClient) -> None:
    res = client.post(
        "/api/v1/media/sign", json={"resource_type": "events", "resource_id": str(uuid.uuid4())}
    )
    assert res.status_code == 422
