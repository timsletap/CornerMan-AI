"""VIS-10: One Euro keypoint smoothing."""

from __future__ import annotations

import numpy as np
import synth

from app.vision import signals, tracking
from app.vision.pipeline import analyze_poses
from app.vision.pose import Poses
from app.vision.types import LEFT_WRIST, NOSE, RIGHT_WRIST, VisionConfig

FILTER_OFF = {"one_euro_min_cutoff": 1e6}


def _jittery_stationary(n_frames: int, sigma_px: float, seed: int) -> dict[int, np.ndarray]:
    rng = np.random.default_rng(seed)
    frames = {}
    for f in range(n_frames):
        kps = synth.fighter()
        kps[:, :2] += rng.normal(0, sigma_px, size=(17, 2))
        frames[f] = kps
    return frames


def _signals(poses: Poses, cfg: VisionConfig) -> signals.Signals:
    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    return signals.build_signals(raw, poses.meta, cfg)


def _peak_index(poses: Poses, cfg: VisionConfig, wrist: int) -> int:
    speed, _ = signals.keypoint_velocity(_signals(poses, cfg), wrist, cfg)
    return int(np.argmax(speed))


def test_stationary_fighter_with_5px_jitter_produces_no_strikes() -> None:
    cfg = synth.config()
    for seed in range(5):
        poses = synth.sequence(600, [_jittery_stationary(600, 5.0, seed)], track_ids=[1])
        assert analyze_poses(poses, cfg).strikes == []


def test_unfiltered_jitter_would_produce_strikes() -> None:
    """The same jitter without the filter crosses the threshold: the filter matters."""
    poses = synth.sequence(600, [_jittery_stationary(600, 5.0, 0)], track_ids=[1])
    assert len(analyze_poses(poses, synth.config(**FILTER_OFF)).strikes) > 0


def test_jitter_is_reduced() -> None:
    poses = synth.sequence(300, [_jittery_stationary(300, 5.0, 1)], track_ids=[1])
    raw_x = _signals(poses, synth.config(**FILTER_OFF)).xy[30:, LEFT_WRIST, 0]
    smooth_x = _signals(poses, synth.config()).xy[30:, LEFT_WRIST, 0]
    assert raw_x.std() > 4.0
    assert smooth_x.std() < 0.5 * raw_x.std()


def test_punch_peak_timing_is_kept_within_one_frame() -> None:
    cfg = synth.config()
    for wrist in (LEFT_WRIST, RIGHT_WRIST):
        for start in (20, 47):
            poses = synth.sequence(
                90, [synth.punching(90, [(start, wrist)], direction=(1.0, -0.3))], track_ids=[1]
            )
            raw_peak = _peak_index(poses, synth.config(**FILTER_OFF), wrist)
            assert raw_peak == start + 1
            assert abs(_peak_index(poses, cfg, wrist) - raw_peak) <= 1
            found = analyze_poses(poses, cfg).strikes  # and the punch is still detected
            assert len(found) == 1
            assert abs(found[0].frame_number - raw_peak) <= 1


def test_low_confidence_points_hold_the_last_filtered_position() -> None:
    cfg = synth.config()
    frames = {}
    for f in range(30):
        kps = synth.fighter()
        if 10 <= f < 20:
            kps[LEFT_WRIST] = (5.0, 5.0, 0.2)  # garbage position, low confidence
        frames[f] = kps
    poses = synth.sequence(30, [frames], track_ids=[1])

    analysis = analyze_poses(poses, cfg)

    guard_x = synth.fighter()[LEFT_WRIST, 0]
    for fk in analysis.frames[10:20]:
        assert abs(fk.keypoints[LEFT_WRIST][0] - guard_x) < 1e-6  # held, not the garbage
        assert fk.keypoints[LEFT_WRIST][2] == 0.2  # still marked low confidence
    assert abs(analysis.frames[25].keypoints[NOSE][0] - synth.fighter()[NOSE, 0]) < 1e-6
    assert analysis.strikes == []


def test_one_euro_starts_at_first_valid_sample_and_handles_gaps() -> None:
    values = np.array([[0.0], [10.0], [10.0], [10.0]])
    t = np.array([0.0, 1 / 30, 2 / 30, 10.0])
    valid = np.array([[False], [True], [True], [True]])
    out = signals.one_euro(values, t, valid, 1.0, 0.0, 1.0)
    assert out[0, 0] == 0.0  # nothing valid yet: raw value passes through
    assert out[1, 0] == 10.0
    assert out[3, 0] == 10.0
