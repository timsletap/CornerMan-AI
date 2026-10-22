"""Shared types and constants for the vision stages.

Units: pixel coordinates in the source frame (origin top-left, y down), times in ms
from video start, frame numbers from 0. Velocities are in frame heights per second
("u/s") until VIS-11 moves them to shoulder widths per second.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings

COCO_KEYPOINTS = {
    0: "nose",
    1: "left_eye",
    2: "right_eye",
    3: "left_ear",
    4: "right_ear",
    5: "left_shoulder",
    6: "right_shoulder",
    7: "left_elbow",
    8: "right_elbow",
    9: "left_wrist",
    10: "right_wrist",
    11: "left_hip",
    12: "right_hip",
    13: "left_knee",
    14: "right_knee",
    15: "left_ankle",
    16: "right_ankle",
}
NUM_KEYPOINTS = 17

# Keypoint indices
NOSE = 0
LEFT_EYE, RIGHT_EYE = 1, 2
LEFT_EAR, RIGHT_EAR = 3, 4
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_ELBOW, RIGHT_ELBOW = 7, 8
LEFT_WRIST, RIGHT_WRIST = 9, 10
LEFT_HIP, RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16

Keypoint = tuple[float, float, float]
"""(x, y, confidence)"""


@dataclass
class FrameKeypoints:
    """The selected fighter in one analyzed frame."""

    frame_number: int
    timestamp_ms: int
    keypoints: list[Keypoint]  # 17 entries of (x, y, conf)
    bbox: tuple[float, float, float, float]
    bbox_area: float


@dataclass
class StrikeDetection:
    frame_number: int
    timestamp_ms: int
    hand: str
    velocity: float
    velocity_vector: tuple[float, float]
    wrist_position: tuple[float, float]
    strike_type: str = ""
    keypoints_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorDetection:
    frame_number: int
    timestamp_ms: int
    error_type: str
    severity: str
    details: dict[str, Any]
    related_strike_index: int | None = None


@dataclass(frozen=True)
class VideoMeta:
    fps: float
    total_frames: int
    width: int
    height: int


@dataclass(frozen=True)
class VisionConfig:
    """Thresholds and options for the vision stages (see ``app.config`` for meanings)."""

    model_name: str
    frame_skip: int
    occlusion_confidence: float
    occlusion_pause_s: float
    strike_velocity_threshold: float
    guard_distance_threshold: float
    telegraph_variance_threshold: float

    @property
    def skip(self) -> int:
        return max(1, self.frame_skip)

    @classmethod
    def from_settings(cls) -> VisionConfig:
        return cls(
            model_name=settings.YOLO_MODEL_NAME,
            frame_skip=settings.VISION_FRAME_SKIP,
            occlusion_confidence=settings.OCCLUSION_CONFIDENCE_THRESHOLD,
            occlusion_pause_s=settings.OCCLUSION_PAUSE_SECONDS,
            strike_velocity_threshold=settings.STRIKE_VELOCITY_THRESHOLD,
            guard_distance_threshold=settings.GUARD_DISTANCE_THRESHOLD,
            telegraph_variance_threshold=settings.TELEGRAPH_VARIANCE_THRESHOLD,
        )


def poses_cache_path(video_path: str) -> Path:
    """Where stage 1 caches poses for a video: ``<stem>_poses.parquet`` next to it."""
    path = Path(video_path)
    return path.with_name(f"{path.stem}_poses.parquet")
