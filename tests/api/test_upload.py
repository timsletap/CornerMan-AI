"""PLT-01: streaming uploads with a size limit."""

import asyncio
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.config import settings
from app.services import video as video_service
from app.services.video import UploadTooLargeError, stream_upload_to_temp

MB = 1024 * 1024
VALID = {"valid": True, "duration_seconds": 4.0}


def files_under(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()] if path.exists() else []


def post_upload(client: TestClient, size: int, name: str = "clip.mp4") -> object:
    return client.post("/api/v1/videos/upload", files={"file": (name, b"\0" * size, "video/mp4")})


def test_oversized_upload_returns_413_and_leaves_no_file(
    client: TestClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    monkeypatch.setattr(settings, "MAX_VIDEO_SIZE_MB", 1)
    validate = MagicMock(return_value=VALID)
    monkeypatch.setattr("app.api.v1.videos.validate_video_file", validate)

    res = post_upload(client, 2 * MB + 1)

    assert res.status_code == 413
    assert "1MB" in res.json()["detail"]
    assert files_under(upload_dir) == []
    validate.assert_not_called()
    fake_db.add.assert_not_called()


def test_upload_within_limit_is_stored(
    client: TestClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    monkeypatch.setattr(settings, "MAX_VIDEO_SIZE_MB", 1)
    monkeypatch.setattr("app.api.v1.videos.validate_video_file", MagicMock(return_value=VALID))

    res = post_upload(client, MB)

    assert res.status_code == 201, res.text
    assert res.json()["file_size_bytes"] == MB
    stored = files_under(upload_dir)
    assert len(stored) == 1
    assert stored[0].suffix == ".mp4"
    assert "tmp" not in stored[0].parts
    assert stored[0].stat().st_size == MB
    fake_db.add.assert_called_once()


def test_invalid_video_is_rejected_and_deleted(
    client: TestClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = {"valid": False, "error": "No video stream found"}
    monkeypatch.setattr("app.api.v1.videos.validate_video_file", MagicMock(return_value=invalid))

    res = post_upload(client, 1000)

    assert res.status_code == 400
    assert res.json()["detail"] == "No video stream found"
    assert files_under(upload_dir) == []


def test_validator_crash_leaves_no_file(
    client: TestClient, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object) -> dict[str, object]:
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr("app.api.v1.videos.validate_video_file", boom)
    with pytest.raises(FileNotFoundError):
        post_upload(client, 1000)
    assert files_under(upload_dir) == []


def _upload(data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename="clip.mp4")


def test_stream_accepts_exactly_max_bytes(upload_dir: Path) -> None:
    path, size = asyncio.run(stream_upload_to_temp(_upload(b"x" * 10), 10, ".mp4"))
    assert size == 10
    assert path.read_bytes() == b"x" * 10


def test_stream_rejects_one_byte_over(upload_dir: Path) -> None:
    with pytest.raises(UploadTooLargeError):
        asyncio.run(stream_upload_to_temp(_upload(b"x" * 11), 10, ".mp4"))
    assert files_under(upload_dir) == []


def test_stream_reads_in_1mb_chunks(upload_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upload = _upload(b"x" * (2 * MB + 5))
    sizes: list[int] = []
    original_read = upload.read

    async def spy(size: int = -1) -> bytes:
        sizes.append(size)
        return await original_read(size)

    monkeypatch.setattr(upload, "read", spy)
    asyncio.run(stream_upload_to_temp(upload, 10 * MB, ".mp4"))
    assert sizes and all(s == video_service.UPLOAD_CHUNK_BYTES == MB for s in sizes)
