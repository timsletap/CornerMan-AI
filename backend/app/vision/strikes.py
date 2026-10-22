"""Stage 3a: strike detection from wrist velocity peaks, and strike classification.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.vision.signals import compute_angle, frame_at, wrist_velocities
from app.vision.types import (
    COCO_KEYPOINTS,
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    NUM_KEYPOINTS,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    FrameKeypoints,
    StrikeDetection,
    VideoMeta,
    VisionConfig,
)

DEBOUNCE_SECONDS = 0.3
"""Minimum time between two strikes by the same hand."""


def detect_strikes(
    frames: Sequence[FrameKeypoints],
    active_frames: set[int],
    meta: VideoMeta,
    cfg: VisionConfig,
) -> list[StrikeDetection]:
    """VIS-02: local wrist-velocity maxima above the threshold, debounced, classified."""
    strikes: list[StrikeDetection] = []
    if len(frames) < 3:
        return strikes

    for hand_idx, hand_name in [(LEFT_WRIST, "left"), (RIGHT_WRIST, "right")]:
        velocities = wrist_velocities(frames, active_frames, hand_idx, meta)

        threshold = cfg.strike_velocity_threshold
        min_gap_frames = int(meta.fps * DEBOUNCE_SECONDS)
        last_strike_frame = -min_gap_frames

        for i in range(1, len(velocities) - 1):
            mag = velocities[i][0]
            if mag > threshold and mag >= velocities[i - 1][0] and mag >= velocities[i + 1][0]:
                fk = frames[i + 1]
                if fk.frame_number - last_strike_frame < min_gap_frames:
                    continue

                snapshot = {
                    COCO_KEYPOINTS[k]: {
                        "x": round(fk.keypoints[k][0], 1),
                        "y": round(fk.keypoints[k][1], 1),
                        "confidence": round(fk.keypoints[k][2], 3),
                    }
                    for k in range(NUM_KEYPOINTS)
                }
                strikes.append(
                    StrikeDetection(
                        frame_number=fk.frame_number,
                        timestamp_ms=fk.timestamp_ms,
                        hand=hand_name,
                        velocity=mag,
                        velocity_vector=(velocities[i][1], velocities[i][2]),
                        wrist_position=(fk.keypoints[hand_idx][0], fk.keypoints[hand_idx][1]),
                        keypoints_snapshot=snapshot,
                    )
                )
                last_strike_frame = fk.frame_number

    strikes.sort(key=lambda s: s.frame_number)

    for strike in strikes:
        at = frame_at(frames, strike.frame_number, cfg)
        if at:
            strike.strike_type = classify_strike(at, strike.hand, strike.velocity_vector, meta)
        else:
            strike.strike_type = "other"
    return strikes


def classify_strike(
    fk: FrameKeypoints,
    hand: str,
    velocity_vector: tuple[float, float],
    meta: VideoMeta,
) -> str:
    """Classify strike type using biomechanical heuristics."""
    wrist_idx = LEFT_WRIST if hand == "left" else RIGHT_WRIST
    elbow_idx = LEFT_ELBOW if hand == "left" else RIGHT_ELBOW
    shoulder_idx = LEFT_SHOULDER if hand == "left" else RIGHT_SHOULDER

    wrist = fk.keypoints[wrist_idx]
    elbow = fk.keypoints[elbow_idx]
    shoulder = fk.keypoints[shoulder_idx]
    nose = fk.keypoints[NOSE]
    hip_mid_y = (fk.keypoints[LEFT_HIP][1] + fk.keypoints[RIGHT_HIP][1]) / 2

    dx, dy = velocity_vector

    # Body shot: wrist below shoulder midline
    shoulder_hip_mid = shoulder[1] + (hip_mid_y - shoulder[1]) * 0.3
    if wrist[1] > shoulder_hip_mid:
        return "body_shot"

    # Uppercut: dominant upward movement (negative dy in image coords)
    if abs(dy) > abs(dx) * 1.5 and dy < 0:
        return "uppercut"

    # Hook: large horizontal component + bent elbow
    elbow_angle = compute_angle(shoulder, elbow, wrist)
    if abs(dx) > abs(dy) * 1.2 and elbow_angle < 120:
        return "hook"

    # Cross vs Jab: based on arm extension relative to torso
    arm_ext = ((wrist[0] - shoulder[0]) ** 2 + (wrist[1] - shoulder[1]) ** 2) ** 0.5
    torso_height = abs(nose[1] - hip_mid_y) if nose[2] > 0.5 else meta.height * 0.4
    if torso_height > 0 and arm_ext / torso_height > 0.8:
        return "cross"

    return "jab"
