"""Stage 3a: strike detection from wrist velocity peaks, and strike classification.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.vision.signals import (
    TORSO_PER_SHOULDER_WIDTH,
    Signals,
    keypoint_velocity,
    max_joint_angle,
)
from app.vision.stance import hand_role
from app.vision.types import (
    COCO_KEYPOINTS,
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_SHOULDER,
    LEFT_WRIST,
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
    sig: Signals,
    frames: Sequence[FrameKeypoints],
    active_frames: set[int],
    meta: VideoMeta,
    cfg: VisionConfig,
    stance: str = "orthodox",
) -> list[StrikeDetection]:
    """VIS-02: local wrist-speed maxima above the threshold, debounced, classified.

    Wrist speed is relative to the shoulder midpoint in sw/s (VIS-11), so walking or a
    moving camera does not count as punching. ``frames`` are the smoothed frames that
    ``sig`` was built from (same order). ``stance`` (``orthodox`` or ``southpaw``)
    decides which hand is the lead (VIS-12).
    """
    strikes: list[StrikeDetection] = []
    n = len(sig)
    if n < 3:
        return strikes

    threshold = cfg.strike_velocity_threshold
    min_gap_frames = int(meta.fps * DEBOUNCE_SECONDS)
    for hand_idx, hand_name in [(LEFT_WRIST, "left"), (RIGHT_WRIST, "right")]:
        speed, vector = keypoint_velocity(sig, hand_idx, cfg, active_frames)
        last_strike_frame = -min_gap_frames

        for i in range(2, n - 1):
            mag = float(speed[i])
            if mag > threshold and mag >= speed[i - 1] and mag >= speed[i + 1]:
                fk = frames[i]
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
                px_per_sw = float(sig.scale[i])
                strikes.append(
                    StrikeDetection(
                        frame_number=fk.frame_number,
                        timestamp_ms=fk.timestamp_ms,
                        hand=hand_name,
                        velocity=mag,
                        velocity_vector=(
                            float(vector[i, 0]) * px_per_sw,
                            float(vector[i, 1]) * px_per_sw,
                        ),
                        wrist_position=(fk.keypoints[hand_idx][0], fk.keypoints[hand_idx][1]),
                        keypoints_snapshot=snapshot,
                        index=i,
                    )
                )
                last_strike_frame = fk.frame_number

    strikes.sort(key=lambda s: s.frame_number)
    for strike in strikes:
        strike.hand_role = hand_role(strike.hand, stance)
        strike.strike_type = classify_strike(sig, strike.index, strike.hand, strike.hand_role)
    return strikes


ELBOW_WINDOW_FRAMES = 3
"""Frames after the velocity peak over which the elbow may straighten."""

BODY_LINE_FRACTION = 0.3
"""The body-shot line sits this far from the shoulder midpoint toward the hip midpoint."""


def classify_strike(sig: Signals, index: int, hand: str, role: str) -> str:
    """VIS-12: strike type from the wrist's position and direction at the velocity peak.

    Rules, in order:
      1. ``body_shot``: the wrist is below the line 30% of the way from the shoulder
         midpoint to the hip midpoint.
      2. ``uppercut``: the wrist moves mostly upward (``|dy| > 1.5 |dx|``, rising).
      3. ``hook``: the wrist moves mostly sideways (``|dx| > 1.2 |dy|``) and the elbow
         stays bent (angle at the elbow under 120 degrees through the punch).
      4. otherwise a straight punch: ``jab`` from the lead hand, ``cross`` from the rear.

    The elbow angle is the largest seen from the peak to ``ELBOW_WINDOW_FRAMES`` source
    frames after it: a straight punch is still bent at its velocity peak and only
    straightens at full extension, while a hook stays bent.

    Args:
        index: position of the velocity peak in ``sig``.
        hand: ``left`` or ``right`` (anatomical).
        role: ``lead`` or ``rear`` for that hand under the resolved stance.
    """
    wrist_idx = LEFT_WRIST if hand == "left" else RIGHT_WRIST
    elbow_idx = LEFT_ELBOW if hand == "left" else RIGHT_ELBOW
    shoulder_idx = LEFT_SHOULDER if hand == "left" else RIGHT_SHOULDER

    rel = sig.rel
    wrist = rel[index, wrist_idx]
    hip_mid_y = float(rel[index, LEFT_HIP, 1] + rel[index, RIGHT_HIP, 1]) / 2
    hips_ok = bool(sig.ok(LEFT_HIP)[index] and sig.ok(RIGHT_HIP)[index])
    # Relative to the shoulder midpoint (y = 0); the hips sit about 1.6 sw below it.
    torso = hip_mid_y if hips_ok and hip_mid_y > 0 else TORSO_PER_SHOULDER_WIDTH
    if float(wrist[1]) > BODY_LINE_FRACTION * torso:
        return "body_shot"

    dx, dy = (float(v) for v in (rel[index, wrist_idx] - rel[index - 1, wrist_idx]))
    if abs(dy) > 1.5 * abs(dx) and dy < 0:
        return "uppercut"

    if abs(dx) > 1.2 * abs(dy):
        angle = max_joint_angle(sig, shoulder_idx, elbow_idx, wrist_idx, index, ELBOW_WINDOW_FRAMES)
        if angle is not None and angle < 120:
            return "hook"

    return "jab" if role == "lead" else "cross"
