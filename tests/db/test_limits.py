"""PLT-05: daily analysis limit and rolling hourly LLM spend cap (Postgres)."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.analysis import AnalysisSession, AnalysisStatus
from app.models.strike import StrikeEvent
from app.models.usage import LlmSpend, UsageTracking
from app.models.user import User, UserTier
from app.services import usage
from app.tasks import analysis_tasks

MakeUser = Callable[..., tuple[User, dict[str, str]]]
SeedVideo = Callable[..., Any]

VISION_RESULT = {
    "metrics": {"total_strikes": 1, "avg_velocity": 20.0, "guard_score": 80.0},
    "strike_events": [
        {"strike_type": "jab", "hand": "left", "timestamp_ms": 500, "frame_number": 15}
    ],
    "error_flags": [],
}


@pytest.fixture
def no_celery(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    delay = MagicMock()
    monkeypatch.setattr("app.api.v1.analysis.run_analysis_pipeline.delay", delay)
    return delay


def test_sixth_analysis_in_a_day_returns_429(
    db_client: TestClient,
    make_user: MakeUser,
    seed_video: SeedVideo,
    no_celery: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FREE_TIER_DAILY_UPLOADS", 5)
    user, headers = make_user()
    video_id = seed_video(user, n_sessions=0).video.id

    for _ in range(5):
        res = db_client.post(f"/api/v1/videos/{video_id}/analyze", headers=headers)
        assert res.status_code == 202, res.text

    res = db_client.post(f"/api/v1/videos/{video_id}/analyze", headers=headers)

    assert res.status_code == 429
    assert "Daily analysis limit reached (5 per day)" in res.json()["detail"]
    assert "UTC" in res.json()["detail"]
    retry_after = int(res.headers["Retry-After"])
    assert 0 < retry_after <= 24 * 3600
    assert no_celery.call_count == 5


def test_daily_limit_is_per_user_and_skips_pro(
    db: Session,
    db_client: TestClient,
    make_user: MakeUser,
    seed_video: SeedVideo,
    no_celery: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FREE_TIER_DAILY_UPLOADS", 1)
    capped, capped_headers = make_user()
    other, other_headers = make_user()
    pro, pro_headers = make_user()
    pro.tier = UserTier.PRO
    db.commit()

    for user, headers, expected in [
        (capped, capped_headers, [202, 429]),
        (other, other_headers, [202, 429]),
        (pro, pro_headers, [202, 202]),
    ]:
        video_id = seed_video(user, n_sessions=0).video.id
        codes = [
            db_client.post(f"/api/v1/videos/{video_id}/analyze", headers=headers).status_code
            for _ in expected
        ]
        assert codes == expected


def test_yesterdays_analyses_do_not_count(db: Session, make_user: MakeUser) -> None:
    user, _ = make_user()
    yesterday = usage.utc_today() - timedelta(days=1)
    db.add(UsageTracking(user_id=user.id, date=yesterday, upload_count=99))
    db.commit()
    assert usage.check_upload_quota(db, user)


def test_next_daily_reset_is_next_utc_midnight() -> None:
    now = datetime(2026, 10, 21, 23, 59, tzinfo=UTC)
    assert usage.next_daily_reset(now) == datetime(2026, 10, 22, tzinfo=UTC)


def test_hourly_spend_counts_only_the_last_hour(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "API_CREDIT_HOURLY_LIMIT", 1.00)
    user, _ = make_user()
    other, _ = make_user()
    now = datetime.now(UTC)
    db.add_all(
        [
            LlmSpend(user_id=user.id, model="m", cost_usd=5.0, created_at=now - timedelta(hours=2)),
            LlmSpend(
                user_id=user.id, model="m", cost_usd=0.6, created_at=now - timedelta(minutes=5)
            ),
            LlmSpend(user_id=other.id, model="m", cost_usd=5.0, created_at=now),
        ]
    )
    db.commit()

    assert usage.hourly_llm_spend(db, user.id, now) == pytest.approx(0.6)
    assert usage.check_llm_spend_quota(db, user.id, now)

    db.add(LlmSpend(user_id=user.id, model="m", cost_usd=0.4, created_at=now))
    db.commit()
    assert not usage.check_llm_spend_quota(db, user.id, now)


@pytest.fixture
def pipeline(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Callable[[AnalysisSession], MagicMock]:
    """Run the Celery task in-process against the test DB with vision and Redis stubbed.
    Returns the mocked LLM coaching call."""
    monkeypatch.setattr(analysis_tasks, "SessionLocal", sessionmaker(bind=db_engine))
    monkeypatch.setattr(analysis_tasks, "get_video_path", lambda video: "/dev/null")
    monkeypatch.setattr(analysis_tasks, "run_vision_analysis", lambda path, sid: VISION_RESULT)
    monkeypatch.setattr(analysis_tasks, "update_progress", lambda *a, **k: None)
    monkeypatch.setattr(analysis_tasks, "clear_progress", lambda *a, **k: None)
    coach = MagicMock(
        return_value={
            "summary": "LLM report",
            "mapped_drills": [],
            "_usage": {"input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.014},
        }
    )
    monkeypatch.setattr(analysis_tasks, "generate_coaching_feedback", coach)

    def run(session: AnalysisSession) -> MagicMock:
        result = analysis_tasks.run_analysis_pipeline.run(str(session.id), str(session.video_id))
        assert result["status"] == "completed"
        return coach

    return run


def _queued_session(db: Session, user: User, seed_video: SeedVideo) -> AnalysisSession:
    video = seed_video(user, n_sessions=0).video
    session = AnalysisSession(user_id=user.id, video_id=video.id, status=AnalysisStatus.QUEUED)
    db.add(session)
    db.commit()
    return session


def test_over_hourly_spend_uses_fallback_but_keeps_vision_results(
    db: Session,
    make_user: MakeUser,
    seed_video: SeedVideo,
    pipeline: Callable[[AnalysisSession], MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "API_CREDIT_HOURLY_LIMIT", 1.00)
    user, _ = make_user()
    db.add(LlmSpend(user_id=user.id, model="m", cost_usd=1.25))
    session = _queued_session(db, user, seed_video)
    sid: uuid.UUID = session.id

    coach = pipeline(session)

    coach.assert_not_called()
    db.expire_all()
    saved = db.get(AnalysisSession, sid)
    assert saved is not None
    assert saved.status == AnalysisStatus.COMPLETED
    assert saved.total_strikes == 1
    assert saved.vision_json == VISION_RESULT
    assert db.query(StrikeEvent).filter(StrikeEvent.session_id == sid).count() == 1
    report = json.loads(saved.coach_feedback)
    assert report["_note"] == analysis_tasks.SPEND_CAP_NOTE
    assert "Detected 1 strikes" in report["summary"]
    assert db.query(LlmSpend).count() == 1  # the fallback costs nothing


def test_under_hourly_spend_calls_llm_and_records_cost(
    db: Session,
    make_user: MakeUser,
    seed_video: SeedVideo,
    pipeline: Callable[[AnalysisSession], MagicMock],
) -> None:
    user, _ = make_user()
    session = _queued_session(db, user, seed_video)
    sid = session.id

    coach = pipeline(session)

    coach.assert_called_once()
    spend = db.query(LlmSpend).one()
    assert (spend.user_id, spend.session_id) == (user.id, sid)
    assert (spend.input_tokens, spend.output_tokens) == (1000, 500)
    assert spend.cost_usd == pytest.approx(0.014)
    assert spend.model == settings.ANTHROPIC_MODEL
