"""VIS-11: body-relative units (shoulder widths)."""

from __future__ import annotations

import numpy as np
import pytest
import synth

from app.vision import signals, tracking
from app.vision.pipeline import analyze_poses
from app.vision.types import (
    LEFT_HIP,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
)


def _punch_clip(sw: float, cx: float = 640.0, cy: float = 250.0) -> synth.Poses:
    people = synth.punching(60, [(20, LEFT_WRIST)], sw=sw, cx=cx, cy=cy)
    return synth.sequence(60, [people], track_ids=[1])


def test_same_punch_at_half_and_double_size_has_the_same_velocity() -> None:
    cfg = synth.config()
    speeds = []
    for sw in (50.0, 100.0, 200.0):
        found = analyze_poses(_punch_clip(sw, cy=120.0 * sw / 100), cfg).strikes
        assert len(found) == 1
        speeds.append(found[0].velocity)
    assert speeds[0] == pytest.approx(speeds[1], rel=0.02)
    assert speeds[2] == pytest.approx(speeds[1], rel=0.02)
    assert speeds[1] > 10.0  # a real punch, in sw/s


def test_whole_body_translation_is_not_a_strike() -> None:
    """Walking across the frame moves the wrists fast in pixels but not relative to the body."""
    walk = {f: synth.fighter(cx=200 + 25 * f) for f in range(30)}  # 7.5 sw/s across frame
    poses = synth.sequence(30, [walk], track_ids=[1])
    assert analyze_poses(poses, synth.config()).strikes == []


def test_scale_is_shoulder_width_for_a_front_view() -> None:
    cfg = synth.config()
    poses = synth.sequence(40, [{f: synth.fighter(sw=80) for f in range(40)}], track_ids=[1])
    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    sig = signals.build_signals(raw, poses.meta, cfg)
    assert sig.scale == pytest.approx(np.full(40, 80.0))
    assert sig.rel[:, LEFT_SHOULDER, 0] == pytest.approx(np.full(40, 0.5))


def test_scale_uses_torso_when_shoulders_overlap_or_are_unsure() -> None:
    """Side-on fighter (shoulders nearly overlap) and low-confidence shoulders both
    fall back to torso length / 1.6."""
    side, unsure = {}, {}
    for f in range(40):
        kps = synth.fighter(sw=100)
        kps[LEFT_SHOULDER, 0] = kps[RIGHT_SHOULDER, 0] + 8  # 8 px apart in the image
        side[f] = kps
        kps2 = synth.fighter(sw=100)
        kps2[[LEFT_SHOULDER, RIGHT_SHOULDER], 2] = 0.2
        unsure[f] = kps2
    cfg = synth.config(occlusion_confidence=0.5)
    for person in (side, unsure):
        poses = synth.sequence(40, [person], track_ids=[1])
        raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
        raw_kps = np.array(raw[0].keypoints)
        torso = np.linalg.norm(
            (raw_kps[LEFT_SHOULDER, :2] + raw_kps[RIGHT_SHOULDER, :2]) / 2
            - (raw_kps[LEFT_HIP, :2] + raw_kps[RIGHT_HIP, :2]) / 2
        )
        sig = signals.build_signals(raw, poses.meta, cfg)
        assert sig.scale[20] == pytest.approx(torso / 1.6, rel=0.01)


def test_scale_ignores_single_bad_frames() -> None:
    frames = {f: synth.fighter(sw=100) for f in range(60)}
    frames[30] = synth.fighter(sw=300)  # one wildly wrong detection
    poses = synth.sequence(60, [frames], track_ids=[1])
    cfg = synth.config()
    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    assert signals.body_scale(np.array([fk.keypoints for fk in raw]), np.arange(60) / 30.0)[
        30
    ] == pytest.approx(100.0)


def test_guard_distance_is_reported_in_shoulder_widths() -> None:
    """A dropped off hand is flagged with the same value at any size."""
    values = []
    for sw in (50.0, 150.0):
        people = synth.punching(60, [(20, LEFT_WRIST)], sw=sw, cy=100.0 * sw / 50, drop=1.2)
        errors = analyze_poses(synth.sequence(60, [people], track_ids=[1]), synth.config()).errors
        guard = [e for e in errors if e.error_type == "dropped_guard"]
        assert len(guard) == 1
        assert guard[0].details["off_hand"] == "right"
        assert guard[0].measured_value_sw is not None
        values.append(guard[0].measured_value_sw)
    assert values[0] == pytest.approx(values[1], rel=0.02)
    assert values[0] > 1.0


def test_velocity_is_zero_across_occlusion_gaps_and_low_confidence() -> None:
    cfg = synth.config()
    frames = {f: synth.fighter() for f in range(40) if not 10 <= f < 25}
    for f in frames:
        if f >= 25:
            frames[f][RIGHT_WRIST, 0] += 300  # the hand is somewhere else after the gap
    frames[30][LEFT_WRIST, 2] = 0.1
    poses = synth.sequence(40, [frames], track_ids=[1])
    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    sig = signals.build_signals(raw, poses.meta, cfg)
    speed, _ = signals.keypoint_velocity(sig, RIGHT_WRIST, cfg)
    assert speed.max() < 1e-9  # the jump happened during the gap
    left, _ = signals.keypoint_velocity(sig, LEFT_WRIST, cfg)
    assert left.max() < 1e-9


def test_empty_signals() -> None:
    cfg = synth.config()
    sig = signals.build_signals([], synth.sequence(1, []).meta, cfg)
    assert len(sig) == 0
    speed, vector = signals.keypoint_velocity(sig, LEFT_WRIST, cfg)
    assert speed.shape == (0,) and vector.shape == (0, 2)
