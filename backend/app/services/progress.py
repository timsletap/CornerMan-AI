"""Progress tracking for analysis pipeline via Redis."""

import json
from typing import Any

import redis

from app.config import settings

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(  # type: ignore[no-untyped-call]
            settings.REDIS_URL, decode_responses=True
        )
    return _redis_client


def update_progress(session_id: str, step: str, progress: float, detail: str = "") -> None:
    """Update analysis progress for a session.

    Args:
        session_id: Analysis session UUID string.
        step: Current pipeline step name.
        progress: 0.0 to 1.0 progress fraction.
        detail: Human-readable detail string.
    """
    r = _get_redis()
    data = {
        "step": step,
        "progress": round(progress, 3),
        "detail": detail,
    }
    r.setex(f"analysis_progress:{session_id}", 300, json.dumps(data))


def get_progress(session_id: str) -> dict[str, Any] | None:
    """Get current progress for a session."""
    r = _get_redis()
    raw = r.get(f"analysis_progress:{session_id}")
    if raw:
        data: dict[str, Any] = json.loads(str(raw))
        return data
    return None


def clear_progress(session_id: str) -> None:
    """Remove progress key after completion."""
    r = _get_redis()
    r.delete(f"analysis_progress:{session_id}")
