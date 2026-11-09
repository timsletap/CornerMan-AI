"""VIS-10: One Euro keypoint smoothing."""

from __future__ import annotations

import numpy as np
import synth

from app.vision import signals
from app.vision.pipeline import analyze_poses
from app.vision.types import LEFT_WRIST, NOSE, RIGHT_WRIST


def _jittery_stationary(n_frames: int, sigma_px: float, seed: int) -> dict[int, np.ndarray]:
    rng = np.random.default_rng(seed)
    frames = {}
    for f in range(n_frames):
        kps = synth.fighter()
        kps[:, :2] += rng.normal(0, sigma_px, size=(17, 2))
        frames[f] = kps
    return frames


def test_stationary_fighter_with_5px_jitter_produces_no_strikes() -> None:
    cfg = synth.config()
    for seed in range(5):
        poses = synth.sequence(600, [_jittery_stationary(600, 5.0, seed)], track_ids=[1])
        assert analyze_poses(poses, cfg).strikes == []


def test_jitter_is_reduced() -> None:
    cfg = synth.config()
    poses = synth.sequence(300, [_jittery_stationary(300, 5.0, 1)], track_ids=[1])
    raw = analyze_poses(poses, synth.config(one_euro_min_cutoff=1e6)).frames  # filter off
    smooth = analyze_poses(poses, cfg).frames
    raw_x = np.array([fk.keypoints[LEFT_WRIST][0] for fk in raw])[30:]
    smooth_x = np.array([fk.keypoints[LEFT_WRIST][0] for fk in smooth])[30:]
    assert raw_x.std() > 4.0
    assert smooth_x.std() < 0.5 * raw_x.std()


def _peak_frame(frames: list, wrist: int, meta: object) -> int:
    active = {fk.frame_number for fk in frames}
    vel = signals.wrist_velocities(frames, active, wrist, meta)  # type: ignore[arg-type]
    return int(np.argmax([v[0] for v in vel])) + 1


def test_punch_peak_timing_is_kept_within_one_frame() -> None:
    cfg = synth.config()
    for wrist in (LEFT_WRIST, RIGHT_WRIST):
        for start in (20, 47):
            frames = {}
            offsets = synth.PUNCH_SW
            for f in range(90):
                kps = synth.fighter()
                k = f - start
                if 0 <= k < len(offsets):
                    kps[wrist, 0] += offsets[k] * 100
                    kps[wrist, 1] -= offsets[k] * 30
                frames[f] = kps
            poses = synth.sequence(90, [frames], track_ids=[1])
            from app.vision import tracking

            raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
            smooth = signals.smooth_frames(raw, poses.meta, cfg)
            assert (
                abs(_peak_frame(smooth, wrist, poses.meta) - _peak_frame(raw, wrist, poses.meta))
                <= 1
            )
            # and the punch is still detected
            found = analyze_poses(poses, cfg).strikes
            assert (
                len(found) == 1
                and abs(found[0].frame_number - _peak_frame(raw, wrist, poses.meta)) <= 1
            )


def test_low_confidence_points_hold_the_last_filtered_position() -> None:
    cfg = synth.config()
    frames = {}
    for f in range(30):
        kps = synth.fighter()
        if 10 <= f < 20:
            kps[LEFT_WRIST] = (5.0, 5.0, 0.2)  # garbage position, low confidence
        frames[f] = kps
    poses = synth.sequence(30, [frames], track_ids=[1])
    from app.vision import tracking

    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    smooth = signals.smooth_frames(raw, poses.meta, cfg)
    guard_x = synth.fighter()[LEFT_WRIST, 0]
    for fk in smooth[10:20]:
        assert abs(fk.keypoints[LEFT_WRIST][0] - guard_x) < 1e-6  # held, not the garbage
        assert fk.keypoints[LEFT_WRIST][2] == 0.2  # still marked low confidence
    assert abs(smooth[25].keypoints[NOSE][0] - synth.fighter()[NOSE, 0]) < 1e-6
    assert analyze_poses(poses, cfg).strikes == []


def test_one_euro_starts_at_first_valid_sample_and_handles_gaps() -> None:
    values = np.array([[0.0], [10.0], [10.0], [10.0]])
    t = np.array([0.0, 1 / 30, 2 / 30, 10.0])
    valid = np.array([[False], [True], [True], [True]])
    out = signals.one_euro(values, t, valid, 1.0, 0.0, 1.0)
    assert out[0, 0] == 0.0  # nothing valid yet: raw value passes through
    assert out[1, 0] == 10.0
    assert out[3, 0] == 10.0
