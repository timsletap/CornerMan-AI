"""Stage 2: signals derived from the fighter's keypoints (smoothing, occlusion,
velocity, angles).

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

import numpy as np
import numpy.typing as npt

from app.vision.types import FrameKeypoints, Keypoint, VideoMeta, VisionConfig

Velocity = tuple[float, float, float]
"""(magnitude in frame heights/s, dx px/s, dy px/s)"""


MIN_KEYPOINT_CONF = 0.5
"""Keypoints below this confidence are not trusted: not fed to the filter, no velocity."""

FloatArray = npt.NDArray[np.float64]


def _alpha(dt: FloatArray, cutoff: FloatArray) -> FloatArray:
    """Low-pass smoothing factor for a time step ``dt`` (s) and cutoff frequency (Hz)."""
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


def one_euro(
    values: FloatArray,
    t_s: FloatArray,
    valid: npt.NDArray[np.bool_],
    min_cutoff: float,
    beta: float,
    d_cutoff: float,
) -> FloatArray:
    """One Euro filter (Casiez et al. 2012) over K independent signals.

    The cutoff rises with the signal's speed: heavy smoothing when it is still (kills
    jitter), light smoothing when it moves fast (little lag).

    Args:
        values: (N, K) samples; any unit, ``beta`` is per that unit per second.
        t_s: (N,) sample times in seconds, increasing.
        valid: (N, K) False where a sample must not be used; the output holds the last
            filtered value there (the raw value before the first valid sample).
        min_cutoff: cutoff in Hz at zero speed.
        beta: cutoff increase in Hz per unit of speed.
        d_cutoff: cutoff in Hz for the speed estimate.
    """
    n, k = values.shape
    out = values.astype(np.float64).copy()
    x_hat = np.zeros(k)
    dx_hat = np.zeros(k)
    t_prev = np.zeros(k)
    started = np.zeros(k, dtype=bool)
    for i in range(n):
        ok = valid[i]
        first = ok & ~started
        x_hat[first] = values[i, first]
        dx_hat[first] = 0.0

        cont = ok & started
        if cont.any():
            dt = np.maximum(t_s[i] - t_prev[cont], 1e-6)
            dx = (values[i, cont] - x_hat[cont]) / dt
            a_d = _alpha(dt, np.full(dt.shape, d_cutoff))
            dx_hat[cont] = a_d * dx + (1.0 - a_d) * dx_hat[cont]
            a = _alpha(dt, min_cutoff + beta * np.abs(dx_hat[cont]))
            x_hat[cont] = a * values[i, cont] + (1.0 - a) * x_hat[cont]

        t_prev[ok] = t_s[i]
        started |= ok
        out[i, started] = x_hat[started]
    return out


def smooth_frames(
    frames: Sequence[FrameKeypoints], meta: VideoMeta, cfg: VisionConfig
) -> list[FrameKeypoints]:
    """VIS-10: the fighter's keypoints with pose jitter filtered out.

    One filter per keypoint coordinate. Points below ``MIN_KEYPOINT_CONF`` are not fed
    to the filter; they take the last filtered position and keep their low confidence,
    which marks them as interpolated for later stages.
    """
    if not frames:
        return []
    raw = np.array([fk.keypoints for fk in frames], dtype=np.float64)  # (N, 17, 3)
    n = raw.shape[0]
    unit = float(max(1, meta.height))
    xy = raw[:, :, :2].reshape(n, -1) / unit
    valid = np.repeat(raw[:, :, 2] >= MIN_KEYPOINT_CONF, 2, axis=1)
    t_s = np.array([fk.frame_number for fk in frames], dtype=np.float64) / meta.fps
    smooth = (
        one_euro(
            xy, t_s, valid, cfg.one_euro_min_cutoff, cfg.one_euro_beta, cfg.one_euro_d_cutoff
        ).reshape(n, -1, 2)
        * unit
    )
    return [
        replace(
            fk,
            keypoints=[
                (float(smooth[i, j, 0]), float(smooth[i, j, 1]), fk.keypoints[j][2])
                for j in range(raw.shape[1])
            ],
        )
        for i, fk in enumerate(frames)
    ]


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

        if (
            prev.keypoints[hand_idx][2] < MIN_KEYPOINT_CONF
            or curr.keypoints[hand_idx][2] < MIN_KEYPOINT_CONF
        ):
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
