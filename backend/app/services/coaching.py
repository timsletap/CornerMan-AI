"""Coaching service: the entry points the analysis task and tools call.

The agent, report schema, and grounding check live in ``app.coaching``; this module
turns database rows into its inputs and its ``CoachingReport`` into a plain dict.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import anthropic

from app.coaching import agent
from app.coaching.schema import DrillOption
from app.config import settings

Drills = Iterable[Mapping[str, Any]]
"""Rows of the drills table as dicts: ``id``, ``name``, ``error_type``, ``description``."""


def _options(drills: Drills) -> list[DrillOption]:
    return [
        DrillOption(
            id=str(d["id"]),
            name=d["name"],
            error_type=d["error_type"],
            description=d.get("description", ""),
        )
        for d in drills
    ]


def fallback_report(vision_data: dict[str, Any], note: str, drills: Drills = ()) -> dict[str, Any]:
    """Deterministic report built from vision metrics alone, used when the LLM is not
    called (no API key, or the hourly spend cap is reached). Costs nothing."""
    return agent.fallback_report(vision_data, _options(drills), note).model_dump()


def generate_coaching_feedback(
    vision_data: dict[str, Any],
    user_profile: dict[str, Any],
    drills: Drills = (),
    session_id: str = "",
) -> dict[str, Any]:
    """A grounded ``CoachingReport`` (as a dict) for one analysis. Called from Celery (sync)."""
    options = _options(drills)
    if not settings.ANTHROPIC_API_KEY:
        return agent.fallback_report(vision_data, options, agent.NO_KEY_NOTE).model_dump()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return agent.generate_report(
        client, vision_data, user_profile, options, session_id
    ).model_dump()
