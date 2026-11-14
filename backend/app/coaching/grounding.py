"""Grounding check (AGT-07, AGT-08): every claim must trace back to the vision data.

``violations`` lists what fails; ``apply`` removes or replaces the failing claims and
records each removal in ``removed_claims``. After ``apply`` a report has no violations.

Rules:
  1. A note with ``t_ms`` needs a (non-abstained) strike or error flag within 200 ms.
  2. Every ``evidence_field`` and ``key_metric.source_field`` must resolve to a value in
     the vision data (or, for ``tool:`` paths, a recorded tool result).
  3. ``key_metric.value`` must equal the resolved value rounded to 1 decimal.
  4. Nothing may cite an abstained item; ``one_thing`` may not rest only on
     low-confidence items.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from app.coaching.schema import CoachingReport, KeyMetric, Note

logger = logging.getLogger(__name__)

T_MS_WINDOW = 200
"""A note's time must be within this many ms of a strike or error flag."""

ITEM_LISTS = ("strike_events", "error_flags")

FOOTAGE_ADVICE = (
    "Reshoot before changing your technique: this footage was too hard to read. Film from "
    "the side at chest height, about three metres away, with your whole body in frame and "
    "good light."
)

_MISSING = object()

ToolResults = Mapping[str, Any]
"""Recorded tool results by call id (AGT-12)."""


def resolve(path: str, vision: Mapping[str, Any], tool_results: ToolResults | None = None) -> Any:
    """The value at a dotted path, or ``_MISSING``.

    ``metrics.guard_score`` and ``strike_events.3.velocity`` look into the vision data;
    ``tool:<call_id>.<path>`` looks into a recorded tool result.
    """
    current: Any
    if path.startswith("tool:"):
        call_id, _, rest = path[len("tool:") :].partition(".")
        if tool_results is None or call_id not in tool_results:
            return _MISSING
        current = tool_results[call_id]
        parts = rest.split(".") if rest else []
    else:
        current = vision
        parts = path.split(".") if path else [""]
    for part in parts:
        if isinstance(current, Mapping):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, str | bytes):
            if not part.isdigit() or int(part) >= len(current):
                return _MISSING
            current = current[int(part)]
        else:
            return _MISSING
    return current


def resolves(path: str, vision: Mapping[str, Any], tool_results: ToolResults | None = None) -> bool:
    return resolve(path, vision, tool_results) is not _MISSING


def cited_item(path: str, vision: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The strike or error a path points at or into, if any."""
    parts = path.split(".")
    if len(parts) < 2 or parts[0] not in ITEM_LISTS:
        return None
    item = resolve(".".join(parts[:2]), vision)
    return item if isinstance(item, Mapping) else None


def is_abstained(item: Mapping[str, Any]) -> bool:
    return bool(item.get("abstained"))


def is_low_confidence(item: Mapping[str, Any], threshold: float) -> bool:
    """Abstained, labeled low, or with a numeric confidence under ``threshold``."""
    if is_abstained(item):
        return True
    confidence = item.get("confidence")
    if confidence == "low":
        return True
    return isinstance(confidence, int | float) and confidence < threshold


def _event_times(vision: Mapping[str, Any]) -> list[int]:
    return [
        int(item["timestamp_ms"])
        for name in ITEM_LISTS
        for item in vision.get(name, [])
        if isinstance(item, Mapping) and "timestamp_ms" in item and not is_abstained(item)
    ]


def note_problem(
    note: Note, vision: Mapping[str, Any], tool_results: ToolResults | None = None
) -> str | None:
    """Why a note is ungrounded, or None."""
    if not resolves(note.evidence_field, vision, tool_results):
        return f"evidence_field {note.evidence_field!r} is not in the data"
    item = cited_item(note.evidence_field, vision)
    if item is not None and is_abstained(item):
        return f"evidence_field {note.evidence_field!r} is an item the system was unsure about"
    if note.t_ms is not None and not any(
        abs(note.t_ms - t) <= T_MS_WINDOW for t in _event_times(vision)
    ):
        return f"no strike or error within {T_MS_WINDOW} ms of t_ms={note.t_ms}"
    return None


def key_metric_problem(
    metric: KeyMetric, vision: Mapping[str, Any], tool_results: ToolResults | None = None
) -> str | None:
    value = resolve(metric.source_field, vision, tool_results)
    if value is _MISSING:
        return f"source_field {metric.source_field!r} is not in the data"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return f"source_field {metric.source_field!r} is not a number"
    if abs(round(float(value), 1) - metric.value) > 1e-9:
        return (
            f"value {metric.value} does not match {metric.source_field} = {round(float(value), 1)}"
        )
    return None


def one_thing_problem(
    evidence: Sequence[str], vision: Mapping[str, Any], threshold: float
) -> str | None:
    """AGT-08: ``one_thing`` must not rest only on low-confidence items."""
    items = [item for path in evidence if (item := cited_item(path, vision)) is not None]
    if items and all(is_low_confidence(item, threshold) for item in items):
        return "its only evidence is low-confidence items"
    return None


def violations(
    report: CoachingReport,
    vision: Mapping[str, Any],
    low_confidence_threshold: float = 0.5,
    tool_results: ToolResults | None = None,
) -> list[str]:
    """Every grounding failure in a report; empty when it is fully grounded."""
    found: list[str] = []
    problem = key_metric_problem(report.key_metric, vision, tool_results)
    if problem:
        found.append(f"key_metric: {problem}")
    for i, note in enumerate(report.notes):
        problem = note_problem(note, vision, tool_results)
        if problem:
            found.append(f"notes[{i}]: {problem}")
    problem = one_thing_problem(report.one_thing_evidence, vision, low_confidence_threshold)
    if problem:
        found.append(f"one_thing: {problem}")
    return found


def guard_score_metric(vision: Mapping[str, Any]) -> KeyMetric:
    value = resolve("metrics.guard_score", vision)
    number = float(value) if isinstance(value, int | float) else 100.0
    return KeyMetric(
        name="Guard score", value=round(number, 1), unit="%", source_field="metrics.guard_score"
    )


def apply(
    report: CoachingReport,
    vision: Mapping[str, Any],
    session_id: str = "",
    low_confidence_threshold: float = 0.5,
    tool_results: ToolResults | None = None,
) -> CoachingReport:
    """A copy of ``report`` with ungrounded claims removed or replaced."""
    removed = list(report.removed_claims)

    def drop(claim: str, reason: str) -> None:
        removed.append(f"{claim} [{reason}]")
        logger.info("grounding removed a claim (session %s): %s [%s]", session_id, claim, reason)

    key_metric = report.key_metric
    problem = key_metric_problem(key_metric, vision, tool_results)
    if problem:
        drop(f"key_metric {key_metric.name} = {key_metric.value} {key_metric.unit}", problem)
        key_metric = guard_score_metric(vision)

    notes: list[Note] = []
    for note in report.notes:
        problem = note_problem(note, vision, tool_results)
        if problem:
            drop(f"note: {note.text}", problem)
        else:
            notes.append(note)

    one_thing = report.one_thing
    evidence = [p for p in report.one_thing_evidence if resolves(p, vision, tool_results)]
    problem = one_thing_problem(evidence, vision, low_confidence_threshold)
    if problem:
        drop(f"one_thing: {one_thing}", problem)
        one_thing, evidence = FOOTAGE_ADVICE, []

    return report.model_copy(
        update={
            "key_metric": key_metric,
            "notes": notes,
            "one_thing": one_thing,
            "one_thing_evidence": evidence,
            "removed_claims": removed,
        }
    )
