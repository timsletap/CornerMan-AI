"""Synthetic keypoint builders for vision tests (no model, no video).

Coordinates are pixels in a ``WIDTH`` x ``HEIGHT`` frame, y down. ``fighter`` returns a
front-facing guard pose; ``punch`` moves one wrist out and back over a few frames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa

from app.vision.pose import POSES_SCHEMA, Poses
from app.vision.types import (
    LEFT_ANKLE,
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_EYE,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_EYE,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    VideoMeta,
    VisionConfig,
)

WIDTH, HEIGHT, FPS = 1280, 720, 30.0

# Guard pose relative to the shoulder midpoint, in shoulder widths (sw); x right, y down.
# Image-left is the fighter's right side for a front-facing fighter.
_GUARD = {
    NOSE: (0.0, -0.55),
    LEFT_EYE: (0.08, -0.62),
    RIGHT_EYE: (-0.08, -0.62),
    LEFT_EAR: (0.18, -0.58),
    RIGHT_EAR: (-0.18, -0.58),
    LEFT_SHOULDER: (0.5, 0.0),
    RIGHT_SHOULDER: (-0.5, 0.0),
    LEFT_ELBOW: (0.6, 0.6),
    RIGHT_ELBOW: (-0.6, 0.6),
    LEFT_WRIST: (0.2, -0.35),
    RIGHT_WRIST: (-0.2, -0.35),
    LEFT_HIP: (0.35, 1.6),
    RIGHT_HIP: (-0.35, 1.6),
    LEFT_KNEE: (0.4, 2.4),
    RIGHT_KNEE: (-0.4, 2.4),
    LEFT_ANKLE: (0.45, 3.2),
    RIGHT_ANKLE: (-0.45, 3.2),
}


def fighter(
    cx: float = WIDTH / 2, cy: float = 250.0, sw: float = 100.0, conf: float = 0.9
) -> np.ndarray:
    """(17, 3) keypoints: guard pose with shoulder midpoint at (cx, cy), shoulder width sw."""
    kps = np.zeros((17, 3))
    for idx, (dx, dy) in _GUARD.items():
        kps[idx] = (cx + dx * sw, cy + dy * sw, conf)
    return kps


def bbox(kps: np.ndarray, pad: float = 20.0) -> list[float]:
    xs, ys = kps[:, 0], kps[:, 1]
    return [
        float(xs.min() - pad),
        float(ys.min() - pad),
        float(xs.max() + pad),
        float(ys.max() + pad),
    ]


def punch_offsets(n_frames: int = 6, reach_sw: float = 1.6) -> list[float]:
    """Wrist extension (in sw) per frame: out over the first half, back over the second."""
    half = n_frames // 2
    out = [reach_sw * (i + 1) / half for i in range(half)]
    return out + out[-2::-1] + [0.0] * (n_frames - 2 * half + 1)


def sequence(
    n_frames: int,
    people: list[dict[int, np.ndarray]],
    meta: VideoMeta | None = None,
) -> Poses:
    """Poses from per-person {frame_number: (17, 3) keypoints} maps."""
    meta = meta or VideoMeta(fps=FPS, total_frames=n_frames, width=WIDTH, height=HEIGHT)
    rows = []
    for f in range(n_frames):
        for person in people:
            if f not in person:
                continue
            kps = person[f]
            rows.append(
                {
                    "frame_number": f,
                    "timestamp_ms": int((f / meta.fps) * 1000),
                    "track_id": None,
                    "kp_x": [float(v) for v in kps[:, 0]],
                    "kp_y": [float(v) for v in kps[:, 1]],
                    "kp_conf": [float(v) for v in kps[:, 2]],
                    "bbox": bbox(kps),
                    "bbox_conf": 0.9,
                }
            )
    frames: pd.DataFrame = pa.Table.from_pylist(rows, schema=POSES_SCHEMA).to_pandas()
    return Poses(meta=meta, frames=frames)


def config(**overrides: object) -> VisionConfig:
    values: dict[str, object] = {
        "model_name": "yolov8m-pose.pt",
        "frame_skip": 1,
        "occlusion_confidence": 0.7,
        "occlusion_pause_s": 0.5,
        "strike_velocity_threshold": 1.0,
        "guard_distance_threshold": 0.35,
        "telegraph_variance_threshold": 0.10,
    }
    values.update(overrides)
    return VisionConfig(**values)  # type: ignore[arg-type]
