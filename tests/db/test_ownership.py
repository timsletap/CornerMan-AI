"""QA-03: auth and per-user isolation on every resource route (Postgres, real JWT auth).

User B must get 404 (not 403, which would confirm the resource exists) on every route
that takes one of user A's resource IDs, and nothing of A's may change.
"""

import uuid
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.analysis import AnalysisSession
from app.models.error_flag import ErrorFlag
from app.models.feedback import FeedbackRating
from app.models.user import User
from app.models.video import Video

MakeUser = Callable[..., tuple[User, dict[str, str]]]
SeedVideo = Callable[..., Any]

# (method, path template, JSON body template). Placeholders {video_id}, {session_id},
# and {error_flag_id} are filled with user A's IDs.
OWNED_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/v1/videos/{video_id}", None),
    ("PATCH", "/api/v1/videos/{video_id}/trim", {"start_time": 0, "end_time": 1}),
    ("DELETE", "/api/v1/videos/{video_id}", None),
    ("POST", "/api/v1/videos/{video_id}/analyze", None),
    ("GET", "/api/v1/sessions/{session_id}", None),
    ("GET", "/api/v1/sessions/{session_id}/progress", None),
    ("DELETE", "/api/v1/sessions/{session_id}", None),
    ("POST", "/api/v1/sessions/{session_id}/feedback", {"rating": "thumbs_up"}),
    ("POST", "/api/v1/sessions/{session_id}/dispute", {"error_flag_id": "{error_flag_id}"}),
    ("GET", "/api/v1/drills/sessions/{session_id}/recommendations", None),
]

# Loaded by <video> or EventSource with a signed URL instead of a JWT. Isolation is
# enforced when signing (POST /media/sign), tested below per resource type.
SIGNED_ROUTES = {
    ("GET", "/api/v1/videos/{video_id}/stream"): "video",
    ("GET", "/api/v1/sessions/{session_id}/annotated-stream"): "annotated",
    ("GET", "/api/v1/sessions/{session_id}/events"): "events",
}


def _fill(template: Any, ids: dict[str, str]) -> Any:
    if isinstance(template, str):
        return template.format(**ids)
    if isinstance(template, dict):
        return {k: _fill(v, ids) for k, v in template.items()}
    return template


def test_every_resource_route_is_covered() -> None:
    """Fails when a new route takes a resource ID but is missing from the tables above."""
    covered = {(m, p) for m, p, _ in OWNED_ROUTES} | set(SIGNED_ROUTES)
    with_ids = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and "{" in route.path
        for method in route.methods
    }
    assert with_ids - covered == set(), "add new resource routes to OWNED_ROUTES"
    assert covered - with_ids == set(), "OWNED_ROUTES lists routes that no longer exist"


def _snapshot(db: Session, seeded: Any) -> dict[str, object]:
    db.expire_all()
    sids = [s.id for s in seeded.sessions]

    def count(model: Any, *where: Any) -> int:
        stmt = select(func.count()).select_from(model).where(*where)
        return int(db.execute(stmt).scalar_one())

    video = db.get(Video, seeded.video.id)
    return {
        "video": (video.trim_start, video.trim_end) if video else None,
        "sessions": count(AnalysisSession, AnalysisSession.video_id == seeded.video.id),
        "feedback": count(FeedbackRating, FeedbackRating.session_id.in_(sids)),
        "disputed": count(ErrorFlag, ErrorFlag.session_id.in_(sids), ErrorFlag.user_disputed),
        "files": sorted(str(p) for p in seeded.files if p.exists()),
    }


@pytest.mark.parametrize(("method", "path", "body"), OWNED_ROUTES, ids=lambda v: str(v))
def test_other_user_gets_404_and_changes_nothing(
    db: Session,
    db_client: TestClient,
    make_user: MakeUser,
    seed_video: SeedVideo,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    delay = MagicMock()
    monkeypatch.setattr("app.api.v1.analysis.run_analysis_pipeline.delay", delay)
    owner, _ = make_user()
    _, intruder = make_user()
    seeded = seed_video(owner)
    ids = {
        "video_id": str(seeded.video.id),
        "session_id": str(seeded.sessions[0].id),
        "error_flag_id": str(seeded.flag_ids[0]),
    }
    before = _snapshot(db, seeded)

    res = db_client.request(method, _fill(path, ids), json=_fill(body, ids), headers=intruder)

    assert res.status_code == 404, res.text
    assert _snapshot(db, seeded) == before
    delay.assert_not_called()


@pytest.mark.parametrize("resource_type", sorted(set(SIGNED_ROUTES.values())))
def test_other_user_cannot_sign_media_urls(
    db_client: TestClient, make_user: MakeUser, seed_video: SeedVideo, resource_type: str
) -> None:
    owner, owner_headers = make_user()
    _, intruder = make_user()
    seeded = seed_video(owner)
    rid = str(seeded.video.id if resource_type == "video" else seeded.sessions[0].id)
    body = {"resource_type": resource_type, "resource_id": rid}

    assert db_client.post("/api/v1/media/sign", json=body, headers=intruder).status_code == 404
    assert db_client.post("/api/v1/media/sign", json=body, headers=owner_headers).status_code == 200


def test_list_endpoints_only_show_own_resources(
    db_client: TestClient, make_user: MakeUser, seed_video: SeedVideo
) -> None:
    alice, alice_headers = make_user()
    bob, bob_headers = make_user()
    seed_video(alice)
    bob_video = seed_video(bob, n_sessions=1)

    videos = db_client.get("/api/v1/videos/", headers=bob_headers).json()
    sessions = db_client.get("/api/v1/sessions", headers=bob_headers).json()

    assert [v["id"] for v in videos] == [str(bob_video.video.id)]
    assert [s["id"] for s in sessions] == [str(bob_video.sessions[0].id)]
    assert len(db_client.get("/api/v1/videos/", headers=alice_headers).json()) == 1


def test_owner_can_access_own_resources(
    db_client: TestClient, make_user: MakeUser, seed_video: SeedVideo
) -> None:
    owner, headers = make_user()
    seeded = seed_video(owner)
    sid = seeded.sessions[0].id
    assert db_client.get(f"/api/v1/videos/{seeded.video.id}", headers=headers).status_code == 200
    assert db_client.get(f"/api/v1/sessions/{sid}", headers=headers).status_code == 200
    res = db_client.post(
        f"/api/v1/sessions/{sid}/dispute",
        json={"error_flag_id": str(seeded.flag_ids[0])},
        headers=headers,
    )
    assert res.status_code == 200


PROTECTED = [(m, p) for m, p, _ in OWNED_ROUTES] + [
    ("GET", "/api/v1/users/me"),
    ("GET", "/api/v1/videos/"),
    ("GET", "/api/v1/sessions"),
    ("POST", "/api/v1/media/sign"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED, ids=lambda v: str(v))
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic abc"}],
    ids=["none", "garbage", "wrong-scheme"],
)
def test_protected_routes_require_valid_token(
    db_client: TestClient, method: str, path: str, headers: dict[str, str]
) -> None:
    ids = {"video_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4()), "error_flag_id": "x"}
    assert db_client.request(method, _fill(path, ids), headers=headers).status_code == 401


def test_token_for_deleted_user_is_rejected(
    db: Session, db_client: TestClient, make_user: MakeUser
) -> None:
    user, headers = make_user()
    db.delete(user)
    db.commit()
    assert db_client.get("/api/v1/users/me", headers=headers).status_code in (401, 404)
