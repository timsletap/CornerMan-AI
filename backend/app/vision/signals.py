"""Stage 2: clean signals from the fighter's keypoints.

Raw keypoints become: a body scale per frame (pixels per shoulder width), One Euro
smoothed positions, positions relative to the shoulder midpoint in shoulder widths
(``sw``), and wrist velocities in ``sw/s``. Body-relative units make every threshold
independent of how far the fighter is from the camera and of the video resolution.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from app.vision.types import (
    LEFT_HIP,
    LEFT_SHOULDER,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    FrameKeypoints,
    Keypoint,
    VideoMeta,
    VisionConfig,
)

MIN_KEYPOINT_CONF = 0.5
"""Keypoints below this confidence are not trusted: not fed to the filter, no velocity."""

SCALE_WINDOW_S = 1.0
"""Rolling-median window for the body scale, seconds."""

TORSO_PER_SHOULDER_WIDTH = 1.6
"""Torso length (shoulder midpoint to hip midpoint) divided by shoulder width."""

FILTER_RESET_GAP_S = 0.25
"""A keypoint unseen for longer than this restarts its filter: what happened in
between is unknown, so the old position must not be blended into the new one."""

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]


@dataclass
class Signals:
    """The target fighter's cleaned signals; arrays are indexed by analyzed frame."""

    frame_numbers: npt.NDArray[np.int64]  # (N,)
    timestamps_ms: npt.NDArray[np.int64]  # (N,)
    t_s: FloatArray
    """(N,) seconds from video start."""
    xy: FloatArray
    """(N, 17, 2) smoothed positions, pixels."""
    raw_xy: FloatArray
    """(N, 17, 2) positions as the pose model gave them, pixels."""
    conf: FloatArray
    """(N, 17) raw keypoint confidence; below ``MIN_KEYPOINT_CONF`` the position is held."""
    scale: FloatArray
    """(N,) pixels per shoulder width."""
    rel: FloatArray
    """(N, 17, 2) smoothed positions relative to the shoulder midpoint, in sw."""

    def __len__(self) -> int:
        return len(self.frame_numbers)

    def ok(self, keypoint: int) -> BoolArray:
        """(N,) True where the keypoint is confident."""
        result: BoolArray = self.conf[:, keypoint] >= MIN_KEYPOINT_CONF
        return result


def _alpha(dt: FloatArray, cutoff: FloatArray) -> FloatArray:
    """Low-pass smoothing factor for a time step ``dt`` (s) and cutoff frequency (Hz)."""
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


def one_euro(
    values: FloatArray,
    t_s: FloatArray,
    valid: BoolArray,
    min_cutoff: float,
    beta: float,
    d_cutoff: float,
    speed_unit: FloatArray | None = None,
) -> FloatArray:
    """One Euro filter (Casiez et al. 2012) over K independent signals.

    The cutoff rises with the signal's speed: heavy smoothing when it is still (kills
    jitter), light smoothing when it moves fast (little lag).

    Args:
        values: (N, K) samples; any unit, ``beta`` is per that unit per second.
        speed_unit: (N,) optional size of one speed unit in the unit of ``values``
            at each sample (pixels per shoulder width), so ``beta`` is per
            (speed unit / s) while the values stay in pixels.
        t_s: (N,) sample times in seconds, increasing.
        valid: (N, K) False where a sample must not be used; the output holds the last
            filtered value there (the raw value before the first valid sample). A
            signal with no valid sample for ``FILTER_RESET_GAP_S`` starts afresh.
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
        first = ok & (~started | (t_s[i] - t_prev > FILTER_RESET_GAP_S))
        x_hat[first] = values[i, first]
        dx_hat[first] = 0.0

        cont = ok & ~first
        if cont.any():
            dt = np.maximum(t_s[i] - t_prev[cont], 1e-6)
            dx = (values[i, cont] - x_hat[cont]) / dt
            a_d = _alpha(dt, np.full(dt.shape, d_cutoff))
            dx_hat[cont] = a_d * dx + (1.0 - a_d) * dx_hat[cont]
            speed = np.abs(dx_hat[cont])
            if speed_unit is not None:
                speed = speed / speed_unit[i]
            a = _alpha(dt, min_cutoff + beta * speed)
            x_hat[cont] = a * values[i, cont] + (1.0 - a) * x_hat[cont]

        t_prev[ok] = t_s[i]
        started |= ok
        out[i, started] = x_hat[started]
    return out


def body_scale(raw: FloatArray, t_s: FloatArray) -> FloatArray:
    """VIS-11: pixels per shoulder width for each frame.

    Per frame the scale is the distance between the shoulders. When the torso is also
    visible, ``torso length / 1.6`` is used if it is larger: a fighter turned side-on
    has shoulders that overlap in the image, but their torso keeps its length. With
    low-confidence shoulders the torso estimate is used alone. The result is the median
    over a ``SCALE_WINDOW_S`` window, so single bad frames do not move it.

    Args:
        raw: (N, 17, 3) raw keypoints (x px, y px, confidence).
        t_s: (N,) frame times in seconds.
    """
    n = raw.shape[0]
    ls, rs, lh, rh = (raw[:, i, :] for i in (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP))
    shoulders_ok = (ls[:, 2] >= MIN_KEYPOINT_CONF) & (rs[:, 2] >= MIN_KEYPOINT_CONF)
    hips_ok = (lh[:, 2] >= MIN_KEYPOINT_CONF) & (rh[:, 2] >= MIN_KEYPOINT_CONF)
    shoulder_px = np.linalg.norm(ls[:, :2] - rs[:, :2], axis=1)
    torso_px = np.linalg.norm((ls[:, :2] + rs[:, :2]) / 2 - (lh[:, :2] + rh[:, :2]) / 2, axis=1)
    from_torso = torso_px / TORSO_PER_SHOULDER_WIDTH

    per_frame = np.full(n, np.nan)
    both = shoulders_ok & hips_ok
    per_frame[both] = np.maximum(shoulder_px[both], from_torso[both])
    only_shoulders = shoulders_ok & ~hips_ok
    per_frame[only_shoulders] = shoulder_px[only_shoulders]
    only_hips = ~shoulders_ok & hips_ok
    per_frame[only_hips] = from_torso[only_hips]
    per_frame[per_frame <= 0] = np.nan

    if np.isnan(per_frame).all():
        # No usable shoulders or hips anywhere: fall back to the raw estimate so the
        # units stay finite; confidence checks keep such frames out of the analysis.
        fallback = np.maximum(np.maximum(shoulder_px, from_torso), 1.0)
        return np.asarray(fallback, dtype=np.float64)

    scale = np.empty(n)
    half = SCALE_WINDOW_S / 2
    lo = np.searchsorted(t_s, t_s - half, side="left")
    hi = np.searchsorted(t_s, t_s + half, side="right")
    for i in range(n):
        window = per_frame[lo[i] : hi[i]]
        scale[i] = np.nanmedian(window) if not np.isnan(window).all() else np.nan
    # Frames whose whole window is unusable take the nearest usable scale.
    good = np.flatnonzero(~np.isnan(scale))
    bad = np.flatnonzero(np.isnan(scale))
    if len(bad):
        nearest = good[np.abs(good[None, :] - bad[:, None]).argmin(axis=1)]
        scale[bad] = scale[nearest]
    return scale


def build_signals(frames: Sequence[FrameKeypoints], meta: VideoMeta, cfg: VisionConfig) -> Signals:
    """Stage 2 for the target fighter's frames (VIS-10 smoothing, VIS-11 units).

    One filter per keypoint coordinate. The filter measures speed in shoulder widths
    per second, so it behaves the same at any distance from the camera.
    Low-confidence points are not fed to the filter and hold the last filtered position.
    """
    n = len(frames)
    if n == 0:
        empty = np.zeros((0, 17, 2))
        return Signals(
            frame_numbers=np.zeros(0, dtype=np.int64),
            timestamps_ms=np.zeros(0, dtype=np.int64),
            t_s=np.zeros(0),
            xy=empty,
            raw_xy=empty.copy(),
            conf=np.zeros((0, 17)),
            scale=np.zeros(0),
            rel=empty.copy(),
        )
    raw = np.array([fk.keypoints for fk in frames], dtype=np.float64)  # (N, 17, 3)
    frame_numbers = np.array([fk.frame_number for fk in frames], dtype=np.int64)
    t_s = frame_numbers / meta.fps
    conf = raw[:, :, 2]
    scale = body_scale(raw, t_s)

    valid = np.repeat(conf >= MIN_KEYPOINT_CONF, 2, axis=1)
    xy = one_euro(
        raw[:, :, :2].reshape(n, -1),
        t_s,
        valid,
        cfg.one_euro_min_cutoff,
        cfg.one_euro_beta,
        cfg.one_euro_d_cutoff,
        speed_unit=scale,
    ).reshape(n, -1, 2)
    mid = (xy[:, LEFT_SHOULDER] + xy[:, RIGHT_SHOULDER]) / 2
    return Signals(
        frame_numbers=frame_numbers,
        timestamps_ms=np.array([fk.timestamp_ms for fk in frames], dtype=np.int64),
        t_s=t_s,
        xy=xy,
        raw_xy=raw[:, :, :2].copy(),
        conf=conf,
        scale=scale,
        rel=(xy - mid[:, None, :]) / scale[:, None, None],
    )


def smoothed_frames(frames: Sequence[FrameKeypoints], sig: Signals) -> list[FrameKeypoints]:
    """``frames`` with their keypoint positions replaced by the smoothed ones (pixels)."""
    return [
        replace(
            fk,
            keypoints=[
                (float(sig.xy[i, j, 0]), float(sig.xy[i, j, 1]), fk.keypoints[j][2])
                for j in range(sig.xy.shape[1])
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


def keypoint_velocity(
    sig: Signals, keypoint: int, cfg: VisionConfig, active_frames: set[int] | None = None
) -> tuple[FloatArray, FloatArray]:
    """Velocity of a keypoint relative to the shoulder midpoint.

    Returns:
        speed: (N,) magnitude in sw/s; entry i is the motion from frame i-1 to frame i.
        vector: (N, 2) the same motion as (dx, dy) in sw/s, y down.

    Zero at the first frame, where the keypoint is low-confidence in either frame,
    across gaps longer than two frame skips (occlusion), and on inactive frames.
    """
    n = len(sig)
    speed = np.zeros(n)
    vector = np.zeros((n, 2))
    if n < 2:
        return speed, vector
    dt = np.diff(sig.t_s)
    step = np.diff(sig.frame_numbers)
    ok = sig.ok(keypoint)
    usable = ok[1:] & ok[:-1] & (dt > 0) & (step <= cfg.skip * 2)
    if active_frames is not None:
        usable &= np.array([int(f) in active_frames for f in sig.frame_numbers[1:]])
    delta = np.diff(sig.rel[:, keypoint, :], axis=0)
    safe_dt = np.where(dt > 0, dt, 1.0)
    v = delta / safe_dt[:, None]
    v[~usable] = 0.0
    vector[1:] = v
    speed[1:] = np.linalg.norm(v, axis=1)
    return speed, vector


def max_joint_angle(
    sig: Signals, a: int, b: int, c: int, start: int, frames_after: int
) -> float | None:
    """Largest angle at keypoint ``b`` (degrees) from ``start`` to ``frames_after`` source
    frames later, or None when the three keypoints are never all confident.

    Measured on the unsmoothed keypoints: a joint is fully straight for only a frame or
    two, and the smoothing would flatten exactly that moment.
    """
    best: float | None = None
    first_frame = int(sig.frame_numbers[start])
    for i in range(start, len(sig)):
        if int(sig.frame_numbers[i]) - first_frame > frames_after:
            break
        if min(sig.conf[i, a], sig.conf[i, b], sig.conf[i, c]) < MIN_KEYPOINT_CONF:
            continue
        pa, pb, pc = sig.raw_xy[i, a], sig.raw_xy[i, b], sig.raw_xy[i, c]
        angle = compute_angle(
            (float(pa[0]), float(pa[1]), 1.0),
            (float(pb[0]), float(pb[1]), 1.0),
            (float(pc[0]), float(pc[1]), 1.0),
        )
        best = angle if best is None else max(best, angle)
    return best


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
