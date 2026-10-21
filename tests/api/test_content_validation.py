"""PLT-02: uploads and YouTube imports must be real videos within the duration limit.

Tests marked ``needs_ffprobe`` run the real ffprobe/ffmpeg binaries and are skipped
when they are not on PATH (CI installs ffmpeg).
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings

needs_ffprobe = pytest.mark.skipif(
    shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
    reason="ffmpeg/ffprobe not installed",
)


def files_under(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()] if path.exists() else []


def make_clip(path: Path, seconds: float = 1.0) -> Path:
    """Write a tiny synthetic H.264 clip with ffmpeg."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"testsrc=duration={seconds}:size=64x64:rate=10",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def upload(client: TestClient, path: Path, name: str = "clip.mp4") -> Any:
    with path.open("rb") as f:
        return client.post("/api/v1/videos/upload", files={"file": (name, f, "video/mp4")})


@needs_ffprobe
def test_text_file_renamed_to_mp4_is_rejected(
    client: TestClient, upload_dir: Path, tmp_path: Path
) -> None:
    fake = tmp_path / "notes.txt"
    fake.write_text("definitely not a video\n" * 100)

    res = upload(client, fake, name="notes.mp4")

    assert res.status_code == 400
    assert files_under(upload_dir) == []


@needs_ffprobe
def test_valid_short_clip_passes(
    client: TestClient, upload_dir: Path, tmp_path: Path, fake_db: MagicMock
) -> None:
    res = upload(client, make_clip(tmp_path / "ok.mp4"))

    assert res.status_code == 201, res.text
    assert len(files_under(upload_dir)) == 1
    stored = fake_db.add.call_args.args[0]
    assert stored.duration_seconds == pytest.approx(1.0, abs=0.2)


@needs_ffprobe
def test_clip_over_duration_limit_is_rejected(
    client: TestClient, upload_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "MAX_VIDEO_DURATION_SECONDS", 1)
    res = upload(client, make_clip(tmp_path / "long.mp4", seconds=2.0))

    assert res.status_code == 400
    assert "exceeds" in res.json()["detail"]
    assert files_under(upload_dir) == []


def _fake_download(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "filename": path.name,
        "duration": 99.0,
        "file_size_bytes": path.stat().st_size,
        "s3_key": f"videos/x/{path.name}",
    }


def test_youtube_import_rejects_invalid_content_and_deletes_it(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    downloaded = tmp_path / "yt.mp4"
    downloaded.write_text("not a video")
    monkeypatch.setattr(
        "app.api.v1.youtube.download_youtube_clip", lambda *_a: _fake_download(downloaded)
    )
    monkeypatch.setattr(
        "app.api.v1.youtube.validate_video_file",
        MagicMock(return_value={"valid": False, "error": "No video stream found"}),
    )

    res = client.post("/api/v1/youtube/download", json={"url": "https://youtu.be/x"})

    assert res.status_code == 400
    assert res.json()["detail"] == "No video stream found"
    assert not downloaded.exists()
    fake_db.add.assert_not_called()


def test_youtube_import_uses_probed_duration(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    downloaded = tmp_path / "yt.mp4"
    downloaded.write_bytes(b"\0")
    monkeypatch.setattr(
        "app.api.v1.youtube.download_youtube_clip", lambda *_a: _fake_download(downloaded)
    )
    monkeypatch.setattr(
        "app.api.v1.youtube.validate_video_file",
        MagicMock(return_value={"valid": True, "duration_seconds": 12.5}),
    )

    res = client.post("/api/v1/youtube/download", json={"url": "https://youtu.be/x"})

    assert res.status_code == 201, res.text
    assert fake_db.add.call_args.args[0].duration_seconds == 12.5
