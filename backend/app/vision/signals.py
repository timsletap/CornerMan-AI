"""Stage 2: signals derived from the fighter's keypoints (occlusion, velocity, angles).

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.vision.types import FrameKeypoints, Keypoint, VideoMeta, VisionConfig

Velocity = tuple[float, float, float]
"""(magnitude in frame heights/s, dx px/s, dy px/s)"""


def occluded_ranges(
    frames: Sequence[FrameKeypoints], meta: VideoMeta, cfg: VisionConfig
) -> tuple[list[tuple[int, int]], set[int]]:
    """VIS-07: frame ranges where the fighter was missing for at least
    ``occlusion_pause_s``, and the set of frames still active for analysis."""
    active = {fk.frame_number for fk in frames}
    ranges: list[tuple[int, int]] = []
    if not frames:
        return ranges, active

    skip = cfg.skip
    expected_frames = sorted(range(0, meta.total_frames, skip))
    missing_frames = sorted(set(expected_frames) - active)
    if not missing_frames:
        return ranges, active

    threshold_frames = max(1, int(cfg.occlusion_pause_s * meta.fps / skip))
    current_start = missing_frames[0]
    current_end = missing_frames[0]

    for f in missing_frames[1:]:
        if f <= current_end + skip:
            current_end = f
        else:
            gap_len = (current_end - current_start) // skip + 1
            if gap_len >= threshold_frames:
                ranges.append((current_start, current_end))
                for af in range(current_start, current_end + 1):
                    active.discard(af)
            current_start = f
            current_end = f

    gap_len = (current_end - current_start) // skip + 1
    if gap_len >= threshold_frames:
        ranges.append((current_start, current_end))
    return ranges, active


def wrist_velocities(
    frames: Sequence[FrameKeypoints],
    active_frames: set[int],
    hand_idx: int,
    meta: VideoMeta,
) -> list[Velocity]:
    """Velocity between consecutive analyzed frames; entry i is for frames[i + 1].

    Zero where the frame is inactive or either wrist confidence is below 0.5.
    """
    velocities: list[Velocity] = []
    for i in range(1, len(frames)):
        prev = frames[i - 1]
        curr = frames[i]

        if curr.frame_number not in active_frames:
            velocities.append((0.0, 0.0, 0.0))
            continue

        if prev.keypoints[hand_idx][2] < 0.5 or curr.keypoints[hand_idx][2] < 0.5:
            velocities.append((0.0, 0.0, 0.0))
            continue

        dx = curr.keypoints[hand_idx][0] - prev.keypoints[hand_idx][0]
        dy = curr.keypoints[hand_idx][1] - prev.keypoints[hand_idx][1]
        frame_gap = (curr.frame_number - prev.frame_number) / meta.fps
        if frame_gap <= 0:
            velocities.append((0.0, 0.0, 0.0))
            continue

        vel = (dx**2 + dy**2) ** 0.5 / frame_gap
        vel_norm = vel / max(1, meta.height)
        velocities.append((vel_norm, dx / frame_gap, dy / frame_gap))
    return velocities


def compute_angle(a: Keypoint, b: Keypoint, c: Keypoint) -> float:
    """Angle at point b in degrees (each point is (x, y, conf))."""
    ba = (a[0] - b[0], a[1] - b[1])
    bc = (c[0] - b[0], c[1] - b[1])
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    mag_ba = (ba[0] ** 2 + ba[1] ** 2) ** 0.5
    mag_bc = (bc[0] ** 2 + bc[1] ** 2) ** 0.5
    if mag_ba * mag_bc == 0:
        return 180.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_angle))


def frame_at(
    frames: Sequence[FrameKeypoints], frame_number: int, cfg: VisionConfig
) -> FrameKeypoints | None:
    """The analyzed frame closest to ``frame_number``, if within two frame skips."""
    best = None
    best_dist = float("inf")
    for fk in frames:
        dist = abs(fk.frame_number - frame_number)
        if dist < best_dist:
            best_dist = dist
            best = fk
    return best if best_dist <= cfg.skip * 2 else None
