"""PLT-07: server-sent progress events."""

import json
import time
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import analysis
from app.core import media_signing
from app.models.analysis import AnalysisStatus

PROCESSING = AnalysisStatus.PROCESSING


def events_url(session_id: uuid.UUID) -> str:
    exp = int(time.time()) + 60
    return f"/api/v1/sessions/{session_id}/events?exp={exp}&sig={media_signing.sign('events', session_id, exp)}"


def parse_sse(body: str) -> list[tuple[str, dict[str, object] | None]]:
    """(event, data) pairs; comments come back as (':', None)."""
    frames = []
    for block in body.strip().split("\n\n"):
        if block.startswith(":"):
            frames.append((":", None))
            continue
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        frames.append((fields["event"], json.loads(fields["data"])))
    return frames


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis, "EVENTS_POLL_SECONDS", 0)


def script(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    statuses: list[AnalysisStatus | None],
    progress: list[dict[str, object] | None],
) -> None:
    fake_db.query.return_value.filter.return_value.scalar.side_effect = statuses
    values: Iterator[dict[str, object] | None] = iter(progress)
    monkeypatch.setattr(analysis, "get_progress", lambda _sid: next(values, None))


def test_streams_progress_then_done_and_closes(
    client: TestClient, fake_db: MagicMock, monkeypatch: pytest.MonkeyPatch, fast: None
) -> None:
    step = {"step": "detecting", "progress": 0.4, "detail": "Detecting strikes"}
    script(
        monkeypatch,
        fake_db,
        [AnalysisStatus.QUEUED, PROCESSING, PROCESSING, AnalysisStatus.COMPLETED],
        [None, step, step],
    )

    with client.stream("GET", events_url(uuid.uuid4())) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        body = res.read().decode()  # returns only because the server closed the stream

    assert parse_sse(body) == [
        ("progress", {"stage": "queued", "pct": 0.0, "message": "Waiting in queue..."}),
        ("progress", {"stage": "detecting", "pct": 0.4, "message": "Detecting strikes"}),
        ("done", {"stage": "complete", "pct": 1.0, "message": "Analysis complete!"}),
    ]  # the repeated step is not re-sent


def test_failed_event_carries_message_and_closes(
    client: TestClient, fake_db: MagicMock, monkeypatch: pytest.MonkeyPatch, fast: None
) -> None:
    script(
        monkeypatch,
        fake_db,
        [PROCESSING, AnalysisStatus.FAILED],
        [{"step": "pose", "progress": 0.2, "detail": "Pose"}, {"detail": "Analysis failed: boom"}],
    )

    body = client.get(events_url(uuid.uuid4())).text

    assert parse_sse(body)[-1] == ("failed", {"message": "Analysis failed: boom"})


def test_missing_session_reports_failed(
    client: TestClient, fake_db: MagicMock, monkeypatch: pytest.MonkeyPatch, fast: None
) -> None:
    script(monkeypatch, fake_db, [None], [None])
    assert parse_sse(client.get(events_url(uuid.uuid4())).text) == [
        ("failed", {"message": "Analysis failed."})
    ]


def test_keepalive_when_nothing_changes(
    client: TestClient, fake_db: MagicMock, monkeypatch: pytest.MonkeyPatch, fast: None
) -> None:
    monkeypatch.setattr(analysis, "EVENTS_KEEPALIVE_SECONDS", 0)
    step = {"step": "pose", "progress": 0.1, "detail": "Pose"}
    script(monkeypatch, fake_db, [PROCESSING, PROCESSING, AnalysisStatus.COMPLETED], [step, step])

    events = [e for e, _ in parse_sse(client.get(events_url(uuid.uuid4())).text)]

    assert events == ["progress", ":", "done"]


def test_stream_stops_at_max_duration(
    client: TestClient, fake_db: MagicMock, monkeypatch: pytest.MonkeyPatch, fast: None
) -> None:
    monkeypatch.setattr(analysis, "EVENTS_MAX_SECONDS", 0)
    script(monkeypatch, fake_db, [PROCESSING], [None])
    assert client.get(events_url(uuid.uuid4())).text == ""


def test_events_require_signature(client: TestClient) -> None:
    sid = uuid.uuid4()
    assert client.get(f"/api/v1/sessions/{sid}/events").status_code == 403
    exp = int(time.time()) + 60
    wrong_type = media_signing.sign("annotated", sid, exp)
    assert (
        client.get(f"/api/v1/sessions/{sid}/events?exp={exp}&sig={wrong_type}").status_code == 403
    )


def test_sign_events_url(client: TestClient, fake_db: MagicMock) -> None:
    fake_db.query.return_value.filter.return_value.first.return_value = object()
    sid = uuid.uuid4()
    res = client.post(
        "/api/v1/media/sign", json={"resource_type": "events", "resource_id": str(sid)}
    )
    assert res.status_code == 200
    assert res.json()["url"].startswith(f"/api/v1/sessions/{sid}/events?exp=")
