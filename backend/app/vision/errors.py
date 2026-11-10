"""Stage 3b: technique errors per strike (dropped guard, chicken wing) and guard score.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.vision.signals import MIN_KEYPOINT_CONF, FloatArray, Signals
from app.vision.types import (
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    ErrorDetection,
    StrikeDetection,
    VisionConfig,
)

MIN_TELEGRAPH_FRAMES = 5
"""Fewest confident pre-onset frames needed to judge a telegraph."""


def severity_band(value: float, threshold: float, medium: float, high: float) -> str:
    """``low`` above the threshold, ``medium`` above ``medium`` x, ``high`` above ``high`` x."""
    if value > threshold * high:
        return "high"
    if value > threshold * medium:
        return "medium"
    return "low"


def analyze_guard(
    strikes: Sequence[StrikeDetection],
    sig: Signals,
    cfg: VisionConfig,
) -> list[ErrorDetection]:
    """VIS-03: off-hand wrist too far from the nose at the strike frame.

    The distance is in shoulder widths (VIS-11); ``cfg.guard_distance_threshold`` is in sw.
    """
    errors: list[ErrorDetection] = []
    threshold = cfg.guard_distance_threshold
    for strike_idx, strike in enumerate(strikes):
        i = strike.index
        off_wrist = RIGHT_WRIST if strike.hand == "left" else LEFT_WRIST
        if sig.conf[i, off_wrist] < MIN_KEYPOINT_CONF or sig.conf[i, NOSE] < MIN_KEYPOINT_CONF:
            continue

        distance = float(np.linalg.norm(sig.rel[i, off_wrist] - sig.rel[i, NOSE]))
        if distance > threshold:
            errors.append(
                ErrorDetection(
                    frame_number=strike.frame_number,
                    timestamp_ms=strike.timestamp_ms,
                    error_type="dropped_guard",
                    severity=severity_band(distance, threshold, 1.5, 2.0),
                    details={
                        "off_hand": "right" if strike.hand == "left" else "left",
                        "distance_sw": round(distance, 3),
                        "threshold": threshold,
                    },
                    related_strike_index=strike_idx,
                    measured_value_sw=round(distance, 3),
                )
            )
    return errors


def lateral_offsets(sig: Signals, shoulder: int, elbow: int, indices: Sequence[int]) -> FloatArray:
    """Elbow offset from its shoulder, perpendicular to the torso line, in sw.

    The torso line runs from the shoulder midpoint to the hip midpoint; with unsure
    hips it is taken as vertical. Frames where the elbow or shoulder is unsure are left
    out. The sign is arbitrary: use the range of the result.
    """
    values: list[float] = []
    for i in indices:
        if sig.conf[i, elbow] < MIN_KEYPOINT_CONF or sig.conf[i, shoulder] < MIN_KEYPOINT_CONF:
            continue
        torso = (sig.rel[i, LEFT_HIP] + sig.rel[i, RIGHT_HIP]) / 2  # shoulder midpoint is (0, 0)
        length = float(np.linalg.norm(torso))
        hips_ok = (
            sig.conf[i, LEFT_HIP] >= MIN_KEYPOINT_CONF
            and sig.conf[i, RIGHT_HIP] >= MIN_KEYPOINT_CONF
            and length > 1e-6
        )
        ux, uy = (torso[0] / length, torso[1] / length) if hips_ok else (0.0, 1.0)
        arm = sig.rel[i, elbow] - sig.rel[i, shoulder]
        values.append(float(arm[0] * uy - arm[1] * ux))
    return np.array(values, dtype=np.float64)


def detect_telegraph(
    strikes: Sequence[StrikeDetection],
    sig: Signals,
    cfg: VisionConfig,
) -> list[ErrorDetection]:
    """VIS-13: the elbow flares out before the punch starts (chicken wing).

    For each strike, look at the ``telegraph_window_frames`` analyzed frames ending at
    its motion onset, so the punch itself is not counted. The flag is raised when the
    elbow's lateral offset from its shoulder moves through more than
    ``telegraph_offset_threshold`` sw (max minus min). Severity: ``low`` above the
    threshold, ``medium`` above 1.5x, ``high`` above 2.5x.
    """
    errors: list[ErrorDetection] = []
    threshold = cfg.telegraph_offset_threshold
    for strike_idx, strike in enumerate(strikes):
        elbow = LEFT_ELBOW if strike.hand == "left" else RIGHT_ELBOW
        shoulder = LEFT_SHOULDER if strike.hand == "left" else RIGHT_SHOULDER
        onset = strike.onset_index
        if onset < 0:
            continue
        first = max(0, onset - cfg.telegraph_window_frames + 1)
        # Stay within one continuous stretch of footage (no occlusion gap in the window).
        while first < onset and (
            sig.frame_numbers[onset] - sig.frame_numbers[first]
            > cfg.telegraph_window_frames * cfg.skip * 2
        ):
            first += 1
        offsets = lateral_offsets(sig, shoulder, elbow, range(first, onset + 1))
        if len(offsets) < MIN_TELEGRAPH_FRAMES:
            continue

        swing = float(offsets.max() - offsets.min())
        if swing > threshold:
            errors.append(
                ErrorDetection(
                    frame_number=strike.frame_number,
                    timestamp_ms=strike.timestamp_ms,
                    error_type="chicken_wing",
                    severity=severity_band(swing, threshold, 1.5, 2.5),
                    details={
                        "hand": strike.hand,
                        "elbow_swing_sw": round(swing, 3),
                        "threshold": threshold,
                        "pre_strike_frames_analyzed": len(offsets),
                    },
                    related_strike_index=strike_idx,
                    measured_value_sw=round(swing, 3),
                    window_start_ms=int(sig.timestamps_ms[first]),
                    window_end_ms=int(sig.timestamps_ms[onset]),
                )
            )
    return errors


def guard_score(strikes: Sequence[StrikeDetection], errors: Sequence[ErrorDetection]) -> float:
    """Percentage of strikes where the guard was maintained."""
    if not strikes:
        return 100.0
    guard_errors = sum(1 for e in errors if e.error_type == "dropped_guard")
    score = ((len(strikes) - guard_errors) / len(strikes)) * 100
    return round(max(0.0, score), 1)
