"""Stage 3b: technique errors per strike (dropped guard, chicken wing) and guard score.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.vision.signals import MIN_KEYPOINT_CONF, Signals
from app.vision.types import (
    LEFT_ELBOW,
    LEFT_WRIST,
    NOSE,
    RIGHT_ELBOW,
    RIGHT_WRIST,
    ErrorDetection,
    FrameKeypoints,
    StrikeDetection,
    VisionConfig,
)

TELEGRAPH_WINDOW_FRAMES = 10


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


def detect_telegraph(
    strikes: Sequence[StrikeDetection],
    frames: Sequence[FrameKeypoints],
    cfg: VisionConfig,
) -> list[ErrorDetection]:
    """VIS-04: elbow x variation (coefficient of variation) in the pre-strike frames."""
    errors: list[ErrorDetection] = []
    threshold = cfg.telegraph_variance_threshold
    for strike_idx, strike in enumerate(strikes):
        elbow_idx = LEFT_ELBOW if strike.hand == "left" else RIGHT_ELBOW

        pre_frames = [fk for fk in frames if fk.frame_number < strike.frame_number][
            -TELEGRAPH_WINDOW_FRAMES:
        ]
        if len(pre_frames) < 5:
            continue

        elbow_x_coords = [
            fk.keypoints[elbow_idx][0] for fk in pre_frames if fk.keypoints[elbow_idx][2] >= 0.5
        ]
        if len(elbow_x_coords) < 3:
            continue

        mean_x = sum(elbow_x_coords) / len(elbow_x_coords)
        if mean_x == 0:
            continue
        variance = sum((x - mean_x) ** 2 for x in elbow_x_coords) / len(elbow_x_coords)
        std_x = variance**0.5
        cov = std_x / abs(mean_x)

        if cov > threshold:
            errors.append(
                ErrorDetection(
                    frame_number=strike.frame_number,
                    timestamp_ms=strike.timestamp_ms,
                    error_type="chicken_wing",
                    severity=severity_band(cov, threshold, 1.5, 2.5),
                    details={
                        "hand": strike.hand,
                        "elbow_x_variance": round(cov, 4),
                        "threshold": threshold,
                        "pre_strike_frames_analyzed": len(elbow_x_coords),
                    },
                    related_strike_index=strike_idx,
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
