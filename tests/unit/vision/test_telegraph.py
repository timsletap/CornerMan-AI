"""VIS-13: motion onset and telegraph (chicken wing) detection."""

from __future__ import annotations

import numpy as np
import pytest
import synth
from synth import Punch

from app.vision import strikes
from app.vision.pipeline import Analysis, analyze_poses
from app.vision.types import LEFT_WRIST, RIGHT_WRIST, ErrorDetection

START = 40


def _analyze(punch: Punch, **kwargs: object) -> Analysis:
    people = synth.punching(90, [punch], **kwargs)  # type: ignore[arg-type]
    return analyze_poses(synth.sequence(90, [people], track_ids=[1]), synth.config())


def _wings(analysis: Analysis) -> list[ErrorDetection]:
    return [e for e in analysis.errors if e.error_type == "chicken_wing"]


def test_onset_is_the_last_quiet_frame_before_the_punch() -> None:
    analysis = _analyze(Punch(start=START, wrist=LEFT_WRIST))
    (strike,) = analysis.strikes
    assert abs(strike.frame_number - (START + 1)) <= 1
    assert START - 1 <= strike.onset_index <= START
    assert strike.onset_ms == analysis.frames[strike.onset_index].timestamp_ms
    assert strike.onset_ms < strike.timestamp_ms


def test_motion_onset_walks_back_to_below_the_fraction() -> None:
    speed = np.array([0.0, 0.5, 1.0, 1.9, 2.1, 6.0, 10.0, 4.0])
    assert strikes.motion_onset(speed, 6, 0.2) == 3  # 1.9 < 2.0 <= 2.1
    assert strikes.motion_onset(np.array([5.0, 6.0, 10.0]), 2, 0.2) == 0  # never quiet


def test_elbow_flare_before_the_punch_is_flagged() -> None:
    analysis = _analyze(Punch(start=START, wrist=RIGHT_WRIST, flare=0.5))
    (wing,) = _wings(analysis)
    assert wing.details["hand"] == "right"
    # The smoothing takes the top off a quick flare, so the measured swing is a bit under 0.5.
    assert wing.measured_value_sw is not None and 0.25 < wing.measured_value_sw <= 0.5
    assert wing.window_start_ms is not None and wing.window_end_ms is not None
    assert wing.window_start_ms < wing.window_end_ms <= analysis.strikes[0].timestamp_ms
    assert wing.window_end_ms == analysis.strikes[0].onset_ms


def test_clean_punch_is_not_flagged_although_the_elbow_moves_during_it() -> None:
    for wrist in (LEFT_WRIST, RIGHT_WRIST):
        for kind, direction in (("straight", (1.0, -0.2)), ("bent", (-1.0, 0.0))):
            analysis = _analyze(Punch(start=START, wrist=wrist, kind=kind, direction=direction))
            assert len(analysis.strikes) == 1
            assert _wings(analysis) == []


def test_same_flare_scores_the_same_anywhere_in_the_frame_and_at_any_size() -> None:
    """v1 divided by the elbow's x position, so a flare at x=100 scored 10x one at x=1000."""
    scores = []
    for cx, sw in ((100.0, 30.0), (1000.0, 30.0), (640.0, 120.0)):
        analysis = _analyze(
            Punch(start=START, wrist=LEFT_WRIST, flare=0.4), cx=cx, sw=sw, cy=3.0 * sw
        )
        (wing,) = _wings(analysis)
        scores.append(wing.measured_value_sw)
    assert scores[0] == pytest.approx(scores[1], abs=1e-3)
    assert scores[0] == pytest.approx(scores[2], rel=0.02)


def test_severity_grows_with_the_swing() -> None:
    severities = [
        _wings(_analyze(Punch(start=START, wrist=LEFT_WRIST, flare=flare)))[0].severity
        for flare in (0.4, 0.55, 1.0)
    ]
    assert severities == ["low", "medium", "high"]


def test_leaning_torso_does_not_fake_a_flare() -> None:
    """The offset is measured across the torso line, so a tilted fighter is not flagged."""
    angle = np.deg2rad(20)
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])

    def tilt(frames: dict[int, np.ndarray]) -> dict[int, np.ndarray]:
        out = {}
        for f, kps in frames.items():
            k = kps.copy()
            k[:, :2] = (k[:, :2] - (640, 250)) @ rot.T + (640, 250)
            out[f] = k
        return out

    clean = tilt(synth.punching(90, [Punch(start=START, wrist=LEFT_WRIST)]))
    flared = tilt(synth.punching(90, [Punch(start=START, wrist=LEFT_WRIST, flare=0.5)]))
    cfg = synth.config()
    assert _wings(analyze_poses(synth.sequence(90, [clean], track_ids=[1]), cfg)) == []
    (wing,) = _wings(analyze_poses(synth.sequence(90, [flared], track_ids=[1]), cfg))
    # The smoothing takes the top off a quick flare, so the measured swing is a bit under 0.5.
    assert wing.measured_value_sw is not None and 0.25 < wing.measured_value_sw <= 0.5


def test_too_little_footage_before_the_punch_is_not_judged() -> None:
    analysis = _analyze(Punch(start=3, wrist=LEFT_WRIST, flare=0.5))
    assert _wings(analysis) == []
