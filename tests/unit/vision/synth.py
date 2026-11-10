"""Synthetic keypoint builders for vision tests (no model, no video).

Coordinates are pixels in a ``WIDTH`` x ``HEIGHT`` frame, y down. ``fighter`` returns a
front-facing guard pose; ``punch`` moves one wrist out and back over a few frames.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

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


PUNCH_SW = [0.3, 1.0, 1.6, 1.3, 1.0, 0.7, 0.4, 0.2, 0.0]
"""A realistic punch: wrist extension in sw per frame at 30 fps, fast out (peak speed
between frames 0 and 1, full extension at frame 2), slower back."""


def punch_offsets(n_frames: int = 6, reach_sw: float = 1.6) -> list[float]:
    """Wrist extension (in sw) per frame: out over the first half, back over the second."""
    half = n_frames // 2
    out = [reach_sw * (i + 1) / half for i in range(half)]
    return out + out[-2::-1] + [0.0] * (n_frames - 2 * half + 1)


PoseFn = Callable[[], np.ndarray]


@dataclass(frozen=True)
class Punch:
    """One punch in a synthetic sequence. Distances are in shoulder widths (sw)."""

    start: int
    """Frame of the first wrist motion; speed peaks at ``start + 1``, full extension at
    ``start + 2``."""
    wrist: int
    """LEFT_WRIST or RIGHT_WRIST."""
    direction: tuple[float, float] | None = None
    """Wrist travel per unit of extension as (dx, dy), y down; None uses the sequence's."""
    reach: float = 1.0
    """Multiplier on ``PUNCH_SW``."""
    drop: float = 0.0
    """How far the off hand drops (straight down) while the punch is thrown."""
    drop_frames: tuple[int, int] = (0, 5)
    """Frames relative to ``start`` (inclusive) during which the off hand is dropped."""
    flare: float = 0.0
    """Elbow swing away from the body, peaking 4 frames before ``start`` and back in
    by ``start`` (the telegraph)."""
    elbow_follow: float = 0.5
    """Fraction of the wrist travel the elbow makes during the punch."""
    wrist_start: tuple[float, float] | None = None
    """Wrist position relative to the guard position at the start (e.g. low for body shots)."""


def punching(
    n_frames: int,
    punches: Sequence[Punch | tuple[int, int]],
    *,
    sw: float = 100.0,
    cx: float = WIDTH / 2,
    cy: float = 250.0,
    direction: tuple[float, float] = (1.0, -0.2),
    drop: float = 0.0,
    jitter_px: float = 0.0,
    seed: int = 0,
    pose: PoseFn | None = None,
) -> dict[int, np.ndarray]:
    """One fighter throwing the given punches: {frame_number: (17, 3) keypoints}.

    ``punches`` are ``Punch`` objects or ``(start_frame, wrist)`` pairs using this
    function's ``direction`` and ``drop``. ``pose`` builds the base pose for each frame
    (default: front-facing guard at (cx, cy) with shoulder width ``sw`` px).
    """
    rng = np.random.default_rng(seed)
    specs = [
        p if isinstance(p, Punch) else Punch(start=p[0], wrist=p[1], drop=drop) for p in punches
    ]
    frames: dict[int, np.ndarray] = {}
    for f in range(n_frames):
        kps = pose() if pose is not None else fighter(cx=cx, cy=cy, sw=sw)
        for p in specs:
            k = f - p.start
            left = p.wrist == LEFT_WRIST
            elbow = LEFT_ELBOW if left else RIGHT_ELBOW
            off = RIGHT_WRIST if left else LEFT_WRIST
            dx, dy = p.direction or direction
            if p.wrist_start is not None and -15 <= k < len(PUNCH_SW) + 5:
                kps[p.wrist, 0] += p.wrist_start[0] * sw
                kps[p.wrist, 1] += p.wrist_start[1] * sw
            if 0 <= k < len(PUNCH_SW):
                ext = PUNCH_SW[k] * p.reach * sw
                kps[p.wrist, 0] += ext * dx
                kps[p.wrist, 1] += ext * dy
                kps[elbow, 0] += ext * dx * p.elbow_follow
                kps[elbow, 1] += ext * dy * p.elbow_follow
            if p.drop and p.drop_frames[0] <= k <= p.drop_frames[1]:
                kps[off, 1] += p.drop * sw
            if p.flare and -8 <= k <= 0:
                outward = 1.0 if left else -1.0  # image x of the fighter's own side
                kps[elbow, 0] += outward * p.flare * sw * (1 - abs(k + 4) / 4)
        if jitter_px:
            kps[:, :2] += rng.normal(0, jitter_px, size=(17, 2))
        frames[f] = kps
    return frames


def sequence(
    n_frames: int,
    people: list[dict[int, np.ndarray]],
    meta: VideoMeta | None = None,
    track_ids: list[int | dict[int, int] | None] | None = None,
) -> Poses:
    """Poses from per-person {frame_number: (17, 3) keypoints} maps.

    ``track_ids`` gives each person a tracker id, or a {frame_number: id} map for a
    person whose id changes; by default detections have no id.
    """
    meta = meta or VideoMeta(fps=FPS, total_frames=n_frames, width=WIDTH, height=HEIGHT)
    rows = []
    for f in range(n_frames):
        for i, person in enumerate(people):
            if f not in person:
                continue
            tid = track_ids[i] if track_ids is not None else None
            if isinstance(tid, dict):
                tid = tid.get(f)
            kps = person[f]
            rows.append(
                {
                    "frame_number": f,
                    "timestamp_ms": int((f / meta.fps) * 1000),
                    "track_id": tid,
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
        "strike_velocity_threshold": 6.0,
        "guard_distance_threshold": 0.6,
        "telegraph_variance_threshold": 0.10,
    }
    values.update(overrides)
    return VisionConfig(**values)  # type: ignore[arg-type]
