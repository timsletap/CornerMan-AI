"""Coaching agent (AGT-05, AGT-06): one structured report per analysis.

The model answers by calling the ``submit_coaching_report`` tool. Its input is validated
with Pydantic, retried once with the validation errors if it is wrong, and replaced by a
deterministic report built from the vision metrics if that fails too or the API errors.
Every report, from the model or not, goes through the grounding check before it is
returned.

The tool is not forced with ``tool_choice``: current models reject a forced tool call,
so the prompt asks for the call and a reply without one is treated like invalid input.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from app.coaching import grounding
from app.coaching.schema import (
    SUBMIT_TOOL_NAME,
    CoachingReport,
    DrillOption,
    ErrorKind,
    Note,
    PrescribedDrill,
    ReportSubmission,
    submission_schema,
)
from app.config import settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

FALLBACK_MODEL = "fallback"
MAX_ATTEMPTS = 2
"""The first call plus one retry with the validation errors."""

NO_KEY_NOTE = "AI coaching unavailable — set ANTHROPIC_API_KEY for full analysis"
NO_DRILLS_NOTE = "AI coaching unavailable: no drills are set up to prescribe."
API_ERROR_NOTE = (
    "AI coaching was unavailable for this session. "
    "This basic report is built from your vision metrics."
)
INVALID_NOTE = (
    "AI coaching did not produce a usable report for this session. "
    "This basic report is built from your vision metrics."
)

# Fields the fighter's coach has no use for and that dominate the payload size.
_HIDDEN_ITEM_FIELDS = frozenset({"keypoints", "wrist_position", "frame_number"})

_ONE_THING: dict[ErrorKind, str] = {
    "dropped_guard": "Focus on keeping your guard hand tight to your chin when throwing combinations.",
    "chicken_wing": "Keep your elbow tucked in until the punch leaves: no flare before you throw.",
    "other": "Keep your guard hand tight to your chin and reset your stance after every combination.",
}


@cache
def load_prompt(version: str) -> str:
    """The system prompt for a prompt version (``prompts/<version>.md``)."""
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost of a call from its token counts and the configured per-MTok prices (AGT-09)."""
    return (
        input_tokens * settings.ANTHROPIC_PRICE_INPUT_PER_MTOK / 1e6
        + output_tokens * settings.ANTHROPIC_PRICE_OUTPUT_PER_MTOK / 1e6
    )


def _no_usage() -> dict[str, int | float]:
    return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


def _add_usage(total: dict[str, int | float], message: Any) -> None:
    """Add one response's tokens: a reply we cannot use is still billed."""
    input_tokens = int(message.usage.input_tokens)
    output_tokens = int(message.usage.output_tokens)
    total["input_tokens"] += input_tokens
    total["output_tokens"] += output_tokens
    total["cost_usd"] += cost_usd(input_tokens, output_tokens)


def vision_for_model(vision: Mapping[str, Any], low_confidence_threshold: float) -> dict[str, Any]:
    """The vision data as the model sees it.

    Strikes and errors keep their position in the full data as ``index`` (so
    ``strike_events.3`` means the same thing to the model and to the grounding check)
    and carry ``"confidence": "low"`` when the system was unsure about them (AGT-08).
    """

    def items(name: str) -> list[dict[str, Any]]:
        shown = []
        for index, item in enumerate(vision.get(name, [])):
            entry: dict[str, Any] = {"index": index}
            entry.update((k, v) for k, v in item.items() if k not in _HIDDEN_ITEM_FIELDS)
            if grounding.is_low_confidence(item, low_confidence_threshold):
                entry["confidence"] = "low"
            else:
                entry.pop("confidence", None)
            entry.pop("abstained", None)
            shown.append(entry)
        return shown

    return {
        "metrics": vision.get("metrics", {}),
        "strike_events": items("strike_events"),
        "error_flags": items("error_flags"),
        "video_metadata": vision.get("video_metadata", {}),
        "occluded_ranges": vision.get("occluded_ranges", []),
    }


def build_request(
    vision: Mapping[str, Any],
    profile: Mapping[str, Any],
    drills: Sequence[DrillOption],
    low_confidence_threshold: float,
) -> str:
    """The user message: fighter profile, the drills on offer, and the vision data."""
    sections = {
        "Fighter profile": {
            "stance": profile.get("stance", "unknown"),
            "experience_level": profile.get("experience_level", "unknown"),
            "weight_class": profile.get("weight_class", "unknown"),
        },
        "Drills you may prescribe": [drill.model_dump() for drill in drills],
        "Vision data": vision_for_model(vision, low_confidence_threshold),
    }
    body = "\n\n".join(
        f"## {title}\n\n{json.dumps(content, indent=2)}" for title, content in sections.items()
    )
    return f"{body}\n\nSubmit your report with the `{SUBMIT_TOOL_NAME}` tool."


def submit_tool() -> dict[str, Any]:
    return {
        "name": SUBMIT_TOOL_NAME,
        "description": (
            "Submit the coaching report for this session. Call it exactly once; "
            "it is the only way to answer."
        ),
        "input_schema": submission_schema(),
    }


def _describe(error: ValidationError) -> str:
    return "\n".join(
        f"- {'.'.join(str(part) for part in e['loc']) or 'report'}: {e['msg']}"
        for e in error.errors(include_url=False)
    )


def read_submission(message: Any, drill_ids: frozenset[str]) -> tuple[ReportSubmission | None, str]:
    """The validated report in a response, or None and what was wrong with it."""
    calls = [
        block
        for block in message.content
        if block.type == "tool_use" and block.name == SUBMIT_TOOL_NAME
    ]
    if not calls:
        return None, f"You answered without calling the `{SUBMIT_TOOL_NAME}` tool."
    try:
        submission = ReportSubmission.model_validate(
            calls[0].input, context={"drill_ids": drill_ids}
        )
    except ValidationError as error:
        return None, f"The report you submitted was not valid:\n{_describe(error)}"
    return submission, ""


def _dominant_error(vision: Mapping[str, Any]) -> ErrorKind:
    counts = vision.get("metrics", {}).get("error_counts", {})
    guard, wing = counts.get("dropped_guard", 0), counts.get("chicken_wing", 0)
    return "chicken_wing" if wing > guard else "dropped_guard"


def _fallback_drill(drills: Sequence[DrillOption], error_type: ErrorKind) -> str:
    """A real drill for the error if there is one, else any drill, else none."""
    matching = [drill.id for drill in drills if drill.error_type == error_type]
    return (matching or [drill.id for drill in drills] or [""])[0]


def fallback_report(
    vision: Mapping[str, Any],
    drills: Sequence[DrillOption],
    note: str,
    usage: dict[str, int | float] | None = None,
) -> CoachingReport:
    """Deterministic report built from the vision metrics alone.

    Used when the model is not called (no API key, spend cap) or gave nothing usable.
    ``usage`` carries what failed attempts already cost.
    """
    metrics = vision.get("metrics", {})
    error_type = _dominant_error(vision)
    candidates = [
        Note(
            text=f"Total strikes detected: {metrics.get('total_strikes', 0)}",
            t_ms=None,
            evidence_field="metrics.total_strikes",
        ),
        Note(
            text=f"Strikes per minute: {metrics.get('strikes_per_minute', 0):.1f}",
            t_ms=None,
            evidence_field="metrics.strikes_per_minute",
        ),
        Note(
            text=f"Errors found: {sum(metrics.get('error_counts', {}).values())}",
            t_ms=None,
            evidence_field="metrics.error_counts",
        ),
    ]
    return CoachingReport(
        summary=(
            f"Detected {metrics.get('total_strikes', 0)} strikes with an average velocity of "
            f"{metrics.get('avg_velocity', 0):.1f} sw/s. "
            f"Guard score: {metrics.get('guard_score', 100):.0f}%."
        ),
        key_metric=grounding.guard_score_metric(vision),
        one_thing=_ONE_THING[error_type],
        prescribed_drill=PrescribedDrill(
            error_type=error_type,
            drill_id=_fallback_drill(drills, error_type),
            reasoning=(
                "Guard maintenance is fundamental."
                if error_type == "dropped_guard"
                else "A tucked elbow hides the punch until it is on its way."
            ),
        ),
        notes=[n for n in candidates if grounding.resolves(n.evidence_field, vision)],
        prompt_version=settings.PROMPT_VERSION,
        model=FALLBACK_MODEL,
        usage=usage or _no_usage(),
        note=note,
    )


def generate_report(
    client: anthropic.Anthropic,
    vision: Mapping[str, Any],
    profile: Mapping[str, Any],
    drills: Sequence[DrillOption],
    session_id: str = "",
) -> CoachingReport:
    """Ask the model for a report; validate, retry once, ground, or fall back."""
    if not drills:
        return fallback_report(vision, drills, NO_DRILLS_NOTE)

    threshold = settings.COACHING_LOW_CONFIDENCE_THRESHOLD
    drill_ids = frozenset(drill.id for drill in drills)
    request = build_request(vision, profile, drills, threshold)
    tools: Any = [submit_tool()]
    usage = _no_usage()
    content = request

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            message = client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                system=load_prompt(settings.PROMPT_VERSION),
                tools=tools,
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIError as error:
            logger.warning("coaching call failed (session %s): %s", session_id, error)
            return fallback_report(vision, drills, API_ERROR_NOTE, usage)
        _add_usage(usage, message)

        if message.stop_reason in ("refusal", "max_tokens"):
            # Neither is fixed by asking again with the same budget.
            logger.warning(
                "coaching call stopped with %s (session %s)", message.stop_reason, session_id
            )
            break

        submission, problem = read_submission(message, drill_ids)
        if submission is not None:
            report = CoachingReport(
                **submission.model_dump(),
                prompt_version=settings.PROMPT_VERSION,
                model=settings.ANTHROPIC_MODEL,
                usage=usage,
            )
            return grounding.apply(report, vision, session_id, threshold)

        logger.info("coaching attempt %d rejected (session %s): %s", attempt, session_id, problem)
        # A fresh request with the errors appended, rather than a continued conversation:
        # nothing from the rejected reply has to be replayed to the API.
        content = (
            f"{request}\n\n## Your previous attempt was rejected\n\n{problem}\n\n"
            f"Call `{SUBMIT_TOOL_NAME}` again with a corrected report."
        )

    return fallback_report(vision, drills, INVALID_NOTE, usage)
