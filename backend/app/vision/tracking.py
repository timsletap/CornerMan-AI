"""Choose the fighter to analyze from all detected people (VIS-06 behavior).

Per frame, each person is scored by bbox area (60%) and closeness to the frame center
(40%); people whose mean keypoint confidence is below the occlusion threshold are
ignored. VIS-09 replaces this with track-based selection.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

from app.vision.types import NUM_KEYPOINTS, FrameKeypoints, VideoMeta, VisionConfig


def select_primary_actor(
    keypoints_data: npt.NDArray[np.float32],
    boxes: npt.NDArray[np.float32],
    meta: VideoMeta,
    cfg: VisionConfig,
) -> int | None:
    """Index of the best-scoring person in one frame, or None."""
    if len(boxes) == 0:
        return None

    frame_center = (meta.width / 2, meta.height / 2)
    max_diagonal = (meta.width**2 + meta.height**2) ** 0.5
    frame_area = meta.width * meta.height

    best_idx = None
    best_score = -1.0

    for i, box in enumerate(boxes):
        avg_conf = float(keypoints_data[i][:, 2].mean())
        if avg_conf < cfg.occlusion_confidence:
            continue

        bbox_area = (box[2] - box[0]) * (box[3] - box[1])
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        center_dist = ((cx - frame_center[0]) ** 2 + (cy - frame_center[1]) ** 2) ** 0.5

        area_score = bbox_area / frame_area
        center_score = 1.0 - (center_dist / max_diagonal)

        score = area_score * 0.6 + center_score * 0.4
        if score > best_score:
            best_score = score
            best_idx = i

    return best_idx


def primary_track(poses: pd.DataFrame, meta: VideoMeta, cfg: VisionConfig) -> list[FrameKeypoints]:
    """The selected person in each frame that has one, in frame order.

    Arrays are rebuilt as float32, the dtype the pose model returns, so scores match
    the live pipeline exactly.
    """
    track: list[FrameKeypoints] = []
    if poses.empty:
        return track
    for frame_num, group in poses.groupby("frame_number", sort=True):
        keypoints_data = np.stack(
            [
                np.stack([np.asarray(x), np.asarray(y), np.asarray(c)], axis=1)
                for x, y, c in zip(group["kp_x"], group["kp_y"], group["kp_conf"], strict=True)
            ]
        ).astype(np.float32)
        boxes = np.stack([np.asarray(b) for b in group["bbox"]]).astype(np.float32)

        best = select_primary_actor(keypoints_data, boxes, meta, cfg)
        if best is None:
            continue
        kps = keypoints_data[best]
        box = boxes[best]
        track.append(
            FrameKeypoints(
                frame_number=int(frame_num),
                timestamp_ms=int(group["timestamp_ms"].iloc[0]),
                keypoints=[
                    (float(kps[i][0]), float(kps[i][1]), float(kps[i][2]))
                    for i in range(NUM_KEYPOINTS)
                ],
                bbox=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                bbox_area=float((box[2] - box[0]) * (box[3] - box[1])),
            )
        )
    return track
