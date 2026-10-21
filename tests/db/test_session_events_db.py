"""PLT-07: the event stream sees status commits made by another connection (the worker)."""

import json
from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1 import analysis
from app.models.analysis import AnalysisSession, AnalysisStatus
from app.models.user import User
from app.models.video import Video, VideoStatus


def test_stream_sees_worker_commit(
    db: Session,
    db_engine: Engine,
    make_user: Callable[..., tuple[User, dict[str, str]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(analysis, "EVENTS_POLL_SECONDS", 0)
    monkeypatch.setattr(analysis, "get_progress", lambda _sid: None)
    user, _ = make_user()
    video = Video(
        user_id=user.id,
        original_filename="a.mp4",
        s3_key="k",
        file_size_bytes=1,
        format="mp4",
        status=VideoStatus.PROCESSING,
    )
    db.add(video)
    db.flush()
    session = AnalysisSession(user_id=user.id, video_id=video.id, status=AnalysisStatus.PROCESSING)
    db.add(session)
    db.commit()
    sid = session.id

    stream_db = sessionmaker(bind=db_engine)()
    events = analysis._session_events(sid, stream_db)
    assert next(events).startswith("event: progress")

    worker = sessionmaker(bind=db_engine)()
    worker.query(AnalysisSession).filter(AnalysisSession.id == sid).update(
        {"status": AnalysisStatus.COMPLETED}
    )
    worker.commit()
    worker.close()

    frame = next(events)
    assert frame.startswith("event: done")
    assert json.loads(frame.split("data: ", 1)[1])["pct"] == 1.0
    assert list(events) == []
