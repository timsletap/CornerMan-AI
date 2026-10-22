"""Stage 1: pose inference for every person in every analyzed frame, and the poses cache.

The cache (``poses.parquet``) lets stages 2 and 3 rerun in seconds without the model.
One row per detected person per analyzed frame; frames with no detections have no rows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.vision.types import NUM_KEYPOINTS, VideoMeta, VisionConfig

POSES_SCHEMA = pa.schema(
    [
        ("frame_number", pa.int64()),
        ("timestamp_ms", pa.int64()),
        ("track_id", pa.int64()),  # null until VIS-09
        ("kp_x", pa.list_(pa.float64(), NUM_KEYPOINTS)),
        ("kp_y", pa.list_(pa.float64(), NUM_KEYPOINTS)),
        ("kp_conf", pa.list_(pa.float64(), NUM_KEYPOINTS)),
        ("bbox", pa.list_(pa.float64(), 4)),  # x1, y1, x2, y2
        ("bbox_conf", pa.float64()),
    ]
)

# Stored in the parquet metadata; a cache is reused only when these match.
CACHE_KEYS = ("model_name", "frame_skip", "fps", "total_frames", "width", "height")

ProgressFn = Callable[[int, int], None]
"""Called as (frame_number, total_frames) every 10th analyzed frame."""


@dataclass
class Poses:
    meta: VideoMeta
    frames: pd.DataFrame
    """Columns as in ``POSES_SCHEMA``, sorted by frame_number."""


def read_video_meta(cap: cv2.VideoCapture) -> VideoMeta:
    return VideoMeta(
        fps=cap.get(cv2.CAP_PROP_FPS) or 30.0,
        total_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    )


def extract_poses(
    video_path: str, cfg: VisionConfig, on_progress: ProgressFn | None = None
) -> Poses:
    """Run the pose model on every ``cfg.skip``-th frame and keep all detected people."""
    from ultralytics import YOLO  # heavy import; only stage 1 needs it

    model = YOLO(cfg.model_name)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    meta = read_video_meta(cap)
    rows: list[dict[str, Any]] = []
    frame_num = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % cfg.skip != 0:
                frame_num += 1
                continue

            if on_progress is not None and frame_num % 10 == 0:
                on_progress(frame_num, meta.total_frames)

            timestamp_ms = int((frame_num / meta.fps) * 1000)
            results = model(frame, verbose=False)

            if results[0].keypoints is None or len(results[0].keypoints.data) == 0:
                frame_num += 1
                continue

            keypoints_data = results[0].keypoints.data.cpu().numpy()
            boxes = results[0].boxes.xyxy.cpu().numpy()
            box_conf = results[0].boxes.conf.cpu().numpy()
            for i in range(len(boxes)):
                kps = keypoints_data[i]
                rows.append(
                    {
                        "frame_number": frame_num,
                        "timestamp_ms": timestamp_ms,
                        "track_id": None,
                        "kp_x": [float(v) for v in kps[:, 0]],
                        "kp_y": [float(v) for v in kps[:, 1]],
                        "kp_conf": [float(v) for v in kps[:, 2]],
                        "bbox": [float(v) for v in boxes[i]],
                        "bbox_conf": float(box_conf[i]),
                    }
                )
            frame_num += 1
    finally:
        cap.release()

    table = pa.Table.from_pylist(rows, schema=POSES_SCHEMA)
    return Poses(meta=meta, frames=table.to_pandas())


def _cache_metadata(meta: VideoMeta, cfg: VisionConfig) -> dict[str, str]:
    values = {
        "model_name": Path(cfg.model_name).name,
        "frame_skip": cfg.skip,
        "fps": meta.fps,
        "total_frames": meta.total_frames,
        "width": meta.width,
        "height": meta.height,
    }
    return {k: repr(v) for k, v in values.items()}


def write_poses(poses: Poses, path: Path, cfg: VisionConfig) -> None:
    table = pa.Table.from_pandas(poses.frames, schema=POSES_SCHEMA, preserve_index=False)
    table = table.replace_schema_metadata(
        {f"cornerman.{k}": v for k, v in _cache_metadata(poses.meta, cfg).items()}
    )
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)


def read_poses(path: Path, cfg: VisionConfig, meta: VideoMeta) -> Poses | None:
    """Load a cache written for the same video, model, and frame skip; else None."""
    if not path.exists():
        return None
    try:
        table = pq.read_table(path)
    except (OSError, pa.ArrowException):
        return None
    stored = {
        k.decode().removeprefix("cornerman."): v.decode()
        for k, v in (table.schema.metadata or {}).items()
        if k.startswith(b"cornerman.")
    }
    if stored != _cache_metadata(meta, cfg):
        return None
    return Poses(meta=meta, frames=table.cast(POSES_SCHEMA).to_pandas())


def probe_meta(video_path: str) -> VideoMeta:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    try:
        return read_video_meta(cap)
    finally:
        cap.release()
