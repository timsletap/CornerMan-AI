"""Stage 3b: technique errors per strike (dropped guard, chicken wing) and guard score.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.vision.signals import frame_at
from app.vision.types import (
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_WRIST,
    NOSE,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_WRIST,
    ErrorDetection,
    FrameKeypoints,
    StrikeDetection,
    VisionConfig,
)

TELEGRAPH_WINDOW_FRAMES = 10


def analyze_guard(
    strikes: Sequence[StrikeDetection],
    frames: Sequence[FrameKeypoints],
    cfg: VisionConfig,
) -> list[ErrorDetection]:
    """VIS-03: off-hand wrist too far from the nose at the strike frame."""
    errors: list[ErrorDetection] = []
    threshold = cfg.guard_distance_threshold
    for strike_idx, strike in enumerate(strikes):
        fk = frame_at(frames, strike.frame_number, cfg)
        if fk is None:
            continue

        off_wrist_idx = RIGHT_WRIST if strike.hand == "left" else LEFT_WRIST
        off_wrist = fk.keypoints[off_wrist_idx]
        nose = fk.keypoints[NOSE]

        if off_wrist[2] < 0.5 or nose[2] < 0.5:
            continue

        distance = ((off_wrist[0] - nose[0]) ** 2 + (off_wrist[1] - nose[1]) ** 2) ** 0.5
        hip_mid_y = (fk.keypoints[LEFT_HIP][1] + fk.keypoints[RIGHT_HIP][1]) / 2
        torso_height = abs(nose[1] - hip_mid_y)
        if torso_height < 10:
            continue

        normalized_dist = distance / torso_height
        if normalized_dist > threshold:
            if normalized_dist > threshold * 2.0:
                severity = "high"
            elif normalized_dist > threshold * 1.5:
                severity = "medium"
            else:
                severity = "low"

            errors.append(
                ErrorDetection(
                    frame_number=strike.frame_number,
                    timestamp_ms=strike.timestamp_ms,
                    error_type="dropped_guard",
                    severity=severity,
                    details={
                        "off_hand": "right" if strike.hand == "left" else "left",
                        "normalized_distance": round(normalized_dist, 3),
                        "threshold": threshold,
                    },
                    related_strike_index=strike_idx,
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
            if cov > threshold * 2.5:
                severity = "high"
            elif cov > threshold * 1.5:
                severity = "medium"
            else:
                severity = "low"

            errors.append(
                ErrorDetection(
                    frame_number=strike.frame_number,
                    timestamp_ms=strike.timestamp_ms,
                    error_type="chicken_wing",
                    severity=severity,
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
