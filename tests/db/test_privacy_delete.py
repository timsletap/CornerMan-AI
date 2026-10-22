"""PLT-10: deleting a video or session removes every DB row and file derived from it."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisSession
from app.models.error_flag import ErrorFlag
from app.models.feedback import FeedbackRating
from app.models.strike import StrikeEvent
from app.models.user import User
from app.models.video import Video

MakeUser = Callable[..., tuple[User, dict[str, str]]]
SeedVideo = Callable[..., Any]


def count(db: Session, model: type, **filters: object) -> int:
    stmt = select(func.count()).select_from(model).filter_by(**filters)
    return int(db.execute(stmt).scalar_one())


def rows_for_video(db: Session, video_id: uuid.UUID, session_ids: list[uuid.UUID]) -> int:
    db.expire_all()
    total = count(db, Video, id=video_id) + count(db, AnalysisSession, video_id=video_id)
    for sid in session_ids:
        total += count(db, StrikeEvent, session_id=sid)
        total += count(db, ErrorFlag, session_id=sid)
        total += count(db, FeedbackRating, session_id=sid)
    return total


def test_delete_video_removes_all_rows_and_files(
    db: Session, db_client: TestClient, make_user: MakeUser, seed_video: SeedVideo
) -> None:
    user, headers = make_user()
    doomed = seed_video(user)
    keeper = seed_video(user, n_sessions=1)
    doomed_id, doomed_sids = doomed.video.id, [s.id for s in doomed.sessions]
    keeper_id, keeper_sids = keeper.video.id, [s.id for s in keeper.sessions]
    assert rows_for_video(db, doomed_id, doomed_sids) == 9

    res = db_client.delete(f"/api/v1/videos/{doomed_id}", headers=headers)

    assert res.status_code == 204
    assert rows_for_video(db, doomed_id, doomed_sids) == 0
    assert [p for p in doomed.files if p.exists()] == []
    # Another video of the same user is untouched.
    assert all(p.exists() for p in keeper.files)
    assert rows_for_video(db, keeper_id, keeper_sids) == 5


def test_delete_session_removes_only_its_rows_and_files(
    db: Session, db_client: TestClient, make_user: MakeUser, seed_video: SeedVideo
) -> None:
    user, headers = make_user()
    seeded = seed_video(user)
    target_id, other_id = (s.id for s in seeded.sessions)
    video_id = seeded.video.id
    original, raw, poses = seeded.files[0], seeded.files[1], seeded.files[2]

    res = db_client.delete(f"/api/v1/sessions/{target_id}", headers=headers)

    assert res.status_code == 204
    db.expire_all()
    assert count(db, AnalysisSession, id=target_id) == 0
    for model in (StrikeEvent, ErrorFlag, FeedbackRating):
        assert count(db, model, session_id=target_id) == 0
        assert count(db, model, session_id=other_id) == 1
    assert count(db, Video, id=video_id) == 1
    for suffix in ("_annotated", "_annotated_h264"):
        assert not original.with_name(f"{target_id}{suffix}.mp4").exists()
    # The poses cache belongs to the video and is shared with the other session.
    assert original.exists() and raw.exists() and poses.exists()
    assert original.with_name(f"{other_id}_annotated.mp4").exists()


def test_other_user_cannot_delete(
    db: Session, db_client: TestClient, make_user: MakeUser, seed_video: SeedVideo
) -> None:
    owner, _ = make_user()
    _, intruder_headers = make_user()
    seeded = seed_video(owner)

    video_res = db_client.delete(f"/api/v1/videos/{seeded.video.id}", headers=intruder_headers)
    session_res = db_client.delete(
        f"/api/v1/sessions/{seeded.sessions[0].id}", headers=intruder_headers
    )
    assert (video_res.status_code, session_res.status_code) == (404, 404)
    assert all(p.exists() for p in seeded.files)
    assert rows_for_video(db, seeded.video.id, [s.id for s in seeded.sessions]) == 9
