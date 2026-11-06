"""Input validation for every API route (runs fully against the mock-DB fixture).

Invalid inputs are rejected by FastAPI/Pydantic before any handler or DB call, so
these tests never touch the database.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

REGISTER = "/api/v1/users/register"
LOGIN = "/api/v1/users/login"
ME = "/api/v1/users/me"
VIDEOS = "/api/v1/videos/"
SESSIONS = "/api/v1/sessions"
YOUTUBE_SEARCH = "/api/v1/youtube/search"
YOUTUBE_DOWNLOAD = "/api/v1/youtube/download"


def valid_user() -> dict:
    return {
        "email": "fighter@example.com",
        "password": "correct horse battery staple",
        "full_name": "Test Fighter",
    }


# --- users -----


def test_register_rejects_short_password(client: TestClient) -> None:
    body = valid_user() | {"password": "short"}
    res = client.post(REGISTER, json=body)
    assert res.status_code == 422


def test_register_rejects_oversized_password(client: TestClient) -> None:
    body = valid_user() | {"password": "x" * 129}
    res = client.post(REGISTER, json=body)
    assert res.status_code == 422


def test_register_rejects_blank_full_name(client: TestClient) -> None:
    body = valid_user() | {"full_name": "   "}
    res = client.post(REGISTER, json=body)
    assert res.status_code == 422


def test_register_rejects_oversized_full_name(client: TestClient) -> None:
    body = valid_user() | {"full_name": "x" * 256}
    res = client.post(REGISTER, json=body)
    assert res.status_code == 422


def test_register_rejects_invalid_email(client: TestClient) -> None:
    body = valid_user() | {"email": "not-an-email"}
    res = client.post(REGISTER, json=body)
    assert res.status_code == 422


def test_login_rejects_oversized_password(client: TestClient) -> None:
    body = {"email": "fighter@example.com", "password": "x" * 129}
    res = client.post(LOGIN, json=body)
    assert res.status_code == 422


def test_login_rejects_invalid_email(client: TestClient) -> None:
    body = {"email": "", "password": "a" * 8}
    res = client.post(LOGIN, json=body)
    assert res.status_code == 422


def test_update_me_rejects_blank_full_name(client: TestClient) -> None:
    res = client.patch(ME, json={"full_name": "   "})
    assert res.status_code == 422


def test_update_me_rejects_oversized_full_name(client: TestClient) -> None:
    res = client.patch(ME, json={"full_name": "x" * 256})
    assert res.status_code == 422


# --- videos -----


@pytest.mark.parametrize("skip", [-1, -100])
def test_list_videos_rejects_negative_skip(client: TestClient, skip: int) -> None:
    assert client.get(VIDEOS, params={"skip": skip}).status_code == 422


@pytest.mark.parametrize("limit", [0, -5, 101, 10_000])
def test_list_videos_rejects_out_of_range_limit(client: TestClient, limit: int) -> None:
    assert client.get(VIDEOS, params={"limit": limit}).status_code == 422


@pytest.mark.parametrize("payload", [{"start_time": -1}, {"end_time": 0}])
def test_trim_rejects_non_positive_times(client: TestClient, payload: dict) -> None:
    res = client.patch(f"/api/v1/videos/{uuid.uuid4()}/trim", json=payload)
    assert res.status_code == 422


@pytest.mark.parametrize(
    "payload", [{"start_time": 5, "end_time": 5}, {"start_time": 5, "end_time": 1}]
)
def test_trim_rejects_unsorted_times(client: TestClient, payload: dict) -> None:
    res = client.patch(f"/api/v1/videos/{uuid.uuid4()}/trim", json=payload)
    assert res.status_code == 422


def test_upload_rejects_oversized_filename(client: TestClient) -> None:
    name = "x" * 300 + ".mp4"
    res = client.post("/api/v1/videos/upload", files={"file": (name, b"\0", "video/mp4")})
    assert res.status_code == 400
    assert "Filename too long" in res.json()["detail"]


def test_upload_rejects_unallowed_format(client: TestClient) -> None:
    res = client.post("/api/v1/videos/upload", files={"file": ("clip.txt", b"\0", "text/plain")})
    assert res.status_code == 400


# --- analysis sessions -----


@pytest.mark.parametrize("skip", [-1, -100])
def test_list_sessions_rejects_negative_skip(client: TestClient, skip: int) -> None:
    assert client.get(SESSIONS, params={"skip": skip}).status_code == 422


@pytest.mark.parametrize("limit", [0, -5, 101, 10_000])
def test_list_sessions_rejects_out_of_range_limit(client: TestClient, limit: int) -> None:
    assert client.get(SESSIONS, params={"limit": limit}).status_code == 422


def test_feedback_rejects_oversized_comment(client: TestClient) -> None:
    res = client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/feedback",
        json={"rating": "thumbs_up", "comment": "x" * 2001},
    )
    assert res.status_code == 422


def test_feedback_rejects_invalid_rating(client: TestClient) -> None:
    res = client.post(f"/api/v1/sessions/{uuid.uuid4()}/feedback", json={"rating": "meh"})
    assert res.status_code == 422


# --- youtube -----


def test_youtube_search_rejects_blank_query(client: TestClient) -> None:
    res = client.post(YOUTUBE_SEARCH, json={"query": "   ", "max_results": 5})
    assert res.status_code == 422


def test_youtube_search_rejects_empty_query(client: TestClient) -> None:
    res = client.post(YOUTUBE_SEARCH, json={"query": "", "max_results": 5})
    assert res.status_code == 422


@pytest.mark.parametrize("max_results", [0, -1, 51, 10_000])
def test_youtube_search_rejects_out_of_range_max_results(
    client: TestClient, max_results: int
) -> None:
    res = client.post(YOUTUBE_SEARCH, json={"query": "UFC knockout", "max_results": max_results})
    assert res.status_code == 422


@pytest.mark.parametrize(
    "url", ["", "   ", "not-a-url", "youtu.be/x", "ftp://youtu.be/x", "file:///etc/hosts"]
)
def test_youtube_download_rejects_invalid_url(client: TestClient, url: str) -> None:
    res = client.post(YOUTUBE_DOWNLOAD, json={"url": url})
    assert res.status_code == 422


# --- drills -----


def test_drills_reject_unknown_error_type(client: TestClient) -> None:
    res = client.get("/api/v1/drills/", params={"error_type": "garbage"})
    assert res.status_code == 422


def test_drills_accept_known_error_type(client: TestClient, fake_db: MagicMock) -> None:
    fake_db.query.return_value.filter.return_value.all.return_value = []
    res = client.get("/api/v1/drills/", params={"error_type": "dropped_guard"})
    assert res.status_code == 200
    assert res.json() == []


# --- media -----


def test_sign_rejects_invalid_resource_id(client: TestClient) -> None:
    res = client.post("/api/v1/media/sign", json={"resource_type": "video", "resource_id": "nope"})
    assert res.status_code == 422
