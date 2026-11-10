"""VIS-14: guard check over the whole punch."""

from __future__ import annotations

import pytest
import synth
from synth import Punch

from app.vision import errors
from app.vision.pipeline import Analysis, analyze_poses
from app.vision.types import LEFT_WRIST, NOSE, RIGHT_WRIST, ErrorDetection

START = 40


def _analyze(punch: Punch, **kwargs: object) -> Analysis:
    people = synth.punching(90, [punch], **kwargs)  # type: ignore[arg-type]
    return analyze_poses(synth.sequence(90, [people], track_ids=[1]), synth.config())


def _drops(analysis: Analysis) -> list[ErrorDetection]:
    return [e for e in analysis.errors if e.error_type == "dropped_guard"]


def test_guard_that_drops_only_mid_punch_is_flagged() -> None:
    """The off hand is up at the velocity peak and drops two frames later (v1 missed this)."""
    analysis = _analyze(
        Punch(start=START, wrist=LEFT_WRIST, drop=0.9, drop_frames=(1, 8), drop_ramp=5)
    )
    (strike,) = analysis.strikes
    (drop,) = _drops(analysis)

    assert drop.details["off_hand"] == "right"
    assert drop.window_start_ms == strike.onset_ms
    assert drop.window_end_ms is not None and drop.window_end_ms > strike.timestamp_ms
    assert drop.details["worst_ms"] > strike.timestamp_ms  # the drop came after the peak
    assert drop.measured_value_sw is not None and drop.measured_value_sw > 0.6
    assert analysis.guard_score == 0.0

    # At the peak frame itself the off hand is still by the chin.
    sig = analysis.signals
    assert sig is not None
    at_peak = sig.rel[strike.index, RIGHT_WRIST] - sig.rel[strike.index, NOSE]
    assert float((at_peak**2).sum() ** 0.5) < 0.6


def test_tight_guard_throughout_is_not_flagged() -> None:
    for wrist in (LEFT_WRIST, RIGHT_WRIST):
        analysis = _analyze(Punch(start=START, wrist=wrist))
        assert len(analysis.strikes) == 1
        assert _drops(analysis) == []
        assert analysis.guard_score == 100.0


def test_hand_already_low_before_the_punch_is_flagged() -> None:
    analysis = _analyze(Punch(start=START, wrist=RIGHT_WRIST, drop=1.0, drop_frames=(-30, 30)))
    (drop,) = _drops(analysis)
    assert drop.details["off_hand"] == "left"


def test_drop_after_the_window_does_not_count() -> None:
    """Lowering the hand well after the punch has landed is not a guard error on that punch."""
    analysis = _analyze(
        Punch(start=START, wrist=LEFT_WRIST, drop=1.0, drop_frames=(9, 14), drop_ramp=10)
    )
    assert len(analysis.strikes) == 1
    assert _drops(analysis) == []


def test_severity_bands_at_one_and_a_half_and_two_times_the_threshold() -> None:
    severities = []
    for drop in (0.5, 0.8, 1.4):
        punch = Punch(start=START, wrist=LEFT_WRIST, drop=drop, drop_frames=(-20, 10), drop_ramp=14)
        (flag,) = _drops(_analyze(punch))
        severities.append(flag.severity)
    assert severities == ["low", "medium", "high"]
    assert errors.severity_band(1.0, 1.0, 1.5, 2.0) == "low"


def test_unsure_off_hand_is_not_judged() -> None:
    people = synth.punching(90, [Punch(start=START, wrist=LEFT_WRIST, drop=1.2)])
    for kps in people.values():
        kps[RIGHT_WRIST, 2] = 0.2
    analysis = analyze_poses(synth.sequence(90, [people], track_ids=[1]), synth.config())
    assert len(analysis.strikes) == 1
    assert _drops(analysis) == []


def test_same_drop_measures_the_same_at_any_size() -> None:
    values = []
    for sw in (40.0, 160.0):
        analysis = _analyze(Punch(start=START, wrist=LEFT_WRIST, drop=1.0), sw=sw, cy=2.0 * sw)
        values.append(_drops(analysis)[0].measured_value_sw)
    assert values[0] == pytest.approx(values[1], rel=0.02)
