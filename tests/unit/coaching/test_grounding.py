"""AGT-07, AGT-08: claims that cannot be traced to the vision data are removed."""

from typing import Any
from unittest import mock

import pytest

from app.coaching import grounding
from app.coaching.schema import CoachingReport, KeyMetric, Note, PrescribedDrill

VISION: dict[str, Any] = {
    "metrics": {"guard_score": 62.46, "total_strikes": 3, "error_counts": {"dropped_guard": 1}},
    "strike_events": [
        {"timestamp_ms": 1000, "strike_type": "jab", "velocity": 7.0, "confidence": 0.9},
        {"timestamp_ms": 2500, "strike_type": "cross", "abstained": True},
        {"timestamp_ms": 4000, "strike_type": "hook", "confidence": 0.2},
    ],
    "error_flags": [{"timestamp_ms": 1040, "error_type": "dropped_guard"}],
}


def note(text: str, t_ms: int | None, evidence_field: str) -> Note:
    return Note(text=text, t_ms=t_ms, evidence_field=evidence_field)


def report(**changes: Any) -> CoachingReport:
    fields: dict[str, Any] = {
        "summary": "s",
        "key_metric": KeyMetric(
            name="Guard score", value=62.5, unit="%", source_field="metrics.guard_score"
        ),
        "one_thing": "Hands up.",
        "one_thing_evidence": ["error_flags.0"],
        "prescribed_drill": PrescribedDrill(
            error_type="dropped_guard", drill_id="d", reasoning="r"
        ),
        "notes": [note("Guard dropped on the jab.", 1040, "error_flags.0")],
        "prompt_version": "v1",
        "model": "m",
        "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
    }
    fields.update(changes)
    return CoachingReport(**fields)


def test_grounded_report_is_unchanged() -> None:
    original = report()
    assert grounding.violations(original, VISION) == []
    assert grounding.apply(original, VISION) == original


def test_resolve_paths() -> None:
    assert grounding.resolve("metrics.guard_score", VISION) == 62.46
    assert grounding.resolve("strike_events.0.velocity", VISION) == 7.0
    assert grounding.resolve("metrics.error_counts.dropped_guard", VISION) == 1
    for missing in (
        "metrics.nope",
        "strike_events.9",
        "strike_events.x",
        "metrics.guard_score.x",
        "",
    ):
        assert not grounding.resolves(missing, VISION)

    results = {"call_1": {"sessions": [{"guard_score": 70.0}]}}
    assert grounding.resolve("tool:call_1.sessions.0.guard_score", VISION, results) == 70.0
    assert grounding.resolve("tool:call_1", VISION, results) == results["call_1"]
    assert not grounding.resolves("tool:call_2.sessions", VISION, results)
    assert not grounding.resolves("tool:call_1.sessions", VISION)


def test_note_citing_a_nonexistent_timestamp_is_removed() -> None:
    bad = note("Huge overhand at 9 s.", 9000, "strike_events.0")
    original = report(notes=[note("Guard dropped on the jab.", 1040, "error_flags.0"), bad])

    # Patched rather than captured: Alembic's logging setup (DB tests) disables this logger.
    with mock.patch.object(grounding.logger, "info") as log:
        fixed = grounding.apply(original, VISION, session_id="sess-1")

    assert [n.text for n in fixed.notes] == ["Guard dropped on the jab."]
    assert fixed.removed_claims == [
        "note: Huge overhand at 9 s. [no strike or error within 200 ms of t_ms=9000]"
    ]
    logged = log.call_args.args
    assert "sess-1" in logged and "note: Huge overhand at 9 s." in logged
    assert grounding.violations(fixed, VISION) == []


def test_note_time_window_is_200_ms_either_side() -> None:
    assert grounding.note_problem(note("n", 1200, "strike_events.0"), VISION) is None
    assert grounding.note_problem(note("n", 840, "strike_events.0"), VISION) is None
    assert grounding.note_problem(note("n", 1241, "strike_events.0"), VISION) is not None
    # No time claimed, nothing to check.
    assert grounding.note_problem(note("n", None, "metrics.total_strikes"), VISION) is None


def test_notes_with_unknown_or_abstained_evidence_are_removed() -> None:
    original = report(
        notes=[
            note("Made up.", None, "strike_events.7"),
            note("Unsure cross.", None, "strike_events.1.strike_type"),
            # The only event near 2500 ms is the abstained one, which does not count.
            note("Something at 2.5 s.", 2500, "metrics.total_strikes"),
        ]
    )

    fixed = grounding.apply(original, VISION)

    assert fixed.notes == []
    assert len(fixed.removed_claims) == 3
    assert "is not in the data" in fixed.removed_claims[0]
    assert "unsure about" in fixed.removed_claims[1]
    assert "t_ms=2500" in fixed.removed_claims[2]


def test_wrong_key_metric_value_is_replaced() -> None:
    wrong = KeyMetric(name="Guard score", value=90.0, unit="%", source_field="metrics.guard_score")

    fixed = grounding.apply(report(key_metric=wrong), VISION)

    assert fixed.key_metric == KeyMetric(
        name="Guard score", value=62.5, unit="%", source_field="metrics.guard_score"
    )
    assert fixed.removed_claims == [
        "key_metric Guard score = 90.0 % [value 90.0 does not match metrics.guard_score = 62.5]"
    ]


@pytest.mark.parametrize(
    ("source_field", "reason"),
    [
        ("metrics.punch_power", "is not in the data"),
        ("strike_events.0.strike_type", "is not a number"),
    ],
)
def test_key_metric_must_resolve_to_a_number(source_field: str, reason: str) -> None:
    metric = KeyMetric(name="x", value=1.0, unit="", source_field=source_field)

    fixed = grounding.apply(report(key_metric=metric), VISION)

    assert fixed.key_metric.source_field == "metrics.guard_score"
    assert reason in fixed.removed_claims[0]


def test_key_metric_falls_back_to_100_without_a_guard_score() -> None:
    assert grounding.guard_score_metric({}).value == 100.0


def test_one_thing_resting_only_on_low_confidence_items_is_rejected() -> None:
    original = report(
        one_thing="Fix that hook.", one_thing_evidence=["strike_events.2", "strike_events.1"]
    )
    assert grounding.violations(original, VISION) == [
        "one_thing: its only evidence is low-confidence items"
    ]

    fixed = grounding.apply(original, VISION)

    assert fixed.one_thing == grounding.FOOTAGE_ADVICE
    assert fixed.one_thing_evidence == []
    assert fixed.removed_claims == [
        "one_thing: Fix that hook. [its only evidence is low-confidence items]"
    ]


def test_one_thing_with_some_solid_evidence_stands() -> None:
    mixed = report(one_thing_evidence=["strike_events.2", "strike_events.0", "metrics.nope"])

    fixed = grounding.apply(mixed, VISION)

    assert fixed.one_thing == "Hands up."
    assert fixed.one_thing_evidence == ["strike_events.2", "strike_events.0"]  # dead path dropped
    assert fixed.removed_claims == []


def test_low_confidence_threshold_and_labels() -> None:
    assert grounding.is_low_confidence({"confidence": 0.4}, 0.5)
    assert not grounding.is_low_confidence({"confidence": 0.4}, 0.3)
    assert grounding.is_low_confidence({"confidence": "low"}, 0.5)
    assert grounding.is_low_confidence({"abstained": True, "confidence": 0.99}, 0.5)
    assert not grounding.is_low_confidence({}, 0.5)
