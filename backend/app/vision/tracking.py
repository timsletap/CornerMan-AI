"""Choose one fighter and follow them through the clip (VIS-09).

Stage 1 stores a tracker id per detection. Here the target track is picked once, over
the first ``target_select_s`` seconds, by bbox area (60%) and closeness to the frame
center (40%), then followed by id. When the id disappears the target is re-acquired by
bbox overlap within ``reacquire_s``; otherwise the gap is left for the occlusion logic.

A track that was ever in the same frame as the target is another person and is never
taken over, so the analysis cannot jump to a sparring partner.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import pandas as pd

from app.vision.types import NUM_KEYPOINTS, FrameKeypoints, VideoMeta, VisionConfig

BBox = tuple[float, float, float, float]
"""x1, y1, x2, y2 in pixels."""

FALLBACK_MATCH_IOU = 0.3
"""Minimum overlap for the fallback tracker to continue a track."""

TELEPORT_IOU = 0.05
"""Target boxes in consecutive analyzed frames overlapping less than this count as a
suspected identity switch inside the tracker."""


@dataclass(frozen=True)
class Person:
    """One detected person in one frame."""

    frame_number: int
    timestamp_ms: int
    track_id: int
    keypoints: npt.NDArray[np.float64]  # (17, 3): x px, y px, confidence
    bbox: BBox

    @property
    def mean_conf(self) -> float:
        return float(self.keypoints[:, 2].mean())

    @property
    def area(self) -> float:
        return (self.bbox[2] - self.bbox[0]) * (self.bbox[3] - self.bbox[1])


@dataclass(frozen=True)
class TrackSummary:
    """A track as offered to the user for target selection."""

    track_id: int
    first_frame: int
    frames: int
    bbox: BBox
    """Box at the track's first frame, pixels."""
    score: float
    """Selection score over the selection window (0 when absent from it)."""


@dataclass
class TargetTrack:
    frames: list[FrameKeypoints]
    target_track_id: int | None
    """The track chosen at the start (ids taken over later are in ``handoffs``)."""
    handoffs: list[tuple[int, int, int]] = field(default_factory=list)
    """(frame_number, from track id, to track id) for each re-acquisition."""
    identity_switches: int = 0
    """Suspected jumps to another person (see ``TELEPORT_IOU``)."""
    tracks: list[TrackSummary] = field(default_factory=list)


def iou(a: BBox, b: BBox) -> float:
    """Intersection over union of two pixel boxes (0 when either is empty)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _people_by_frame(poses: pd.DataFrame, meta: VideoMeta) -> dict[int, list[Person]]:
    """Detections grouped by frame, with tracker ids (fallback ids where missing)."""
    by_frame: dict[int, list[Person]] = {}
    if poses.empty:
        return by_frame
    missing = poses["track_id"].isna()
    fallback = _FallbackTracker(max_gap_frames=max(1, int(meta.fps)))
    for row, no_id in zip(poses.itertuples(index=False), missing, strict=True):
        frame_number = int(row.frame_number)
        bbox: BBox = tuple(float(v) for v in row.bbox)  # type: ignore[assignment]
        kps = np.stack(
            [
                np.asarray(row.kp_x, dtype=np.float64),
                np.asarray(row.kp_y, dtype=np.float64),
                np.asarray(row.kp_conf, dtype=np.float64),
            ],
            axis=1,
        )
        track_id = fallback.assign(frame_number, bbox) if no_id else int(row.track_id)
        by_frame.setdefault(frame_number, []).append(
            Person(frame_number, int(row.timestamp_ms), track_id, kps, bbox)
        )
    return by_frame


class _FallbackTracker:
    """Greedy IoU tracker for detections that have no tracker id.

    Ids are negative so they never collide with the stage 1 tracker's ids.
    """

    def __init__(self, max_gap_frames: int) -> None:
        self.max_gap = max_gap_frames
        self.last: dict[int, tuple[int, BBox]] = {}
        self.next_id = -1

    def assign(self, frame_number: int, bbox: BBox) -> int:
        best_id, best_iou = None, FALLBACK_MATCH_IOU
        for track_id, (seen, box) in self.last.items():
            if seen == frame_number or frame_number - seen > self.max_gap:
                continue
            overlap = iou(bbox, box)
            if overlap > best_iou:
                best_id, best_iou = track_id, overlap
        if best_id is None:
            best_id = self.next_id
            self.next_id -= 1
        self.last[best_id] = (frame_number, bbox)
        return best_id


def selection_score(person: Person, meta: VideoMeta) -> float:
    """0.6 * bbox area / frame area + 0.4 * centrality (1 at the center, 0 a diagonal away)."""
    cx = (person.bbox[0] + person.bbox[2]) / 2
    cy = (person.bbox[1] + person.bbox[3]) / 2
    dist = ((cx - meta.width / 2) ** 2 + (cy - meta.height / 2) ** 2) ** 0.5
    diagonal = (meta.width**2 + meta.height**2) ** 0.5
    area_norm = person.area / max(1, meta.width * meta.height)
    return float(0.6 * area_norm + 0.4 * (1.0 - dist / diagonal))


def _window_scores(
    by_frame: dict[int, list[Person]],
    start_frame: int,
    meta: VideoMeta,
    cfg: VisionConfig,
    exclude: set[int],
) -> dict[int, float]:
    """Mean selection score per track over ``target_select_s`` from ``start_frame``.

    The mean is over every analyzed frame in the window, so a track seen in one frame
    does not beat one that is there throughout. People below the occlusion confidence
    do not count.
    """
    end_frame = start_frame + cfg.target_select_s * meta.fps
    window = [f for f in sorted(by_frame) if start_frame <= f <= end_frame]
    totals: dict[int, float] = {}
    for f in window:
        for p in by_frame[f]:
            if p.track_id in exclude or p.mean_conf < cfg.occlusion_confidence:
                continue
            totals[p.track_id] = totals.get(p.track_id, 0.0) + selection_score(p, meta)
    return {tid: total / len(window) for tid, total in totals.items()}


def _best(scores: dict[int, float]) -> int | None:
    # Highest score; ties go to the lowest id so the choice is deterministic.
    return min(scores, key=lambda tid: (-scores[tid], tid)) if scores else None


def _to_frame(p: Person) -> FrameKeypoints:
    return FrameKeypoints(
        frame_number=p.frame_number,
        timestamp_ms=p.timestamp_ms,
        keypoints=[
            (float(p.keypoints[i, 0]), float(p.keypoints[i, 1]), float(p.keypoints[i, 2]))
            for i in range(NUM_KEYPOINTS)
        ],
        bbox=p.bbox,
        bbox_area=p.area,
    )


def follow_target(
    poses: pd.DataFrame,
    meta: VideoMeta,
    cfg: VisionConfig,
    target_track_id: int | None = None,
) -> TargetTrack:
    """The target fighter in each frame where they are visible, in frame order.

    Args:
        poses: stage 1 output (``POSES_SCHEMA`` columns), all people in all frames.
        target_track_id: a track id chosen by the user; used when it exists in the clip.
    """
    by_frame = _people_by_frame(poses, meta)
    if not by_frame:
        return TargetTrack(frames=[], target_track_id=None)
    frame_numbers = sorted(by_frame)

    first_seen: dict[int, Person] = {}
    counts: dict[int, int] = {}
    last_frame_of: dict[int, int] = {}
    for f in frame_numbers:
        for p in by_frame[f]:
            first_seen.setdefault(p.track_id, p)
            counts[p.track_id] = counts.get(p.track_id, 0) + 1
            last_frame_of[p.track_id] = f

    scores = _window_scores(by_frame, frame_numbers[0], meta, cfg, set())
    current = target_track_id if target_track_id in first_seen else _best(scores)
    summaries = [
        TrackSummary(tid, p.frame_number, counts[tid], p.bbox, round(scores.get(tid, 0.0), 4))
        for tid, p in sorted(first_seen.items())
    ]
    result = TargetTrack(frames=[], target_track_id=current, tracks=summaries)
    if current is None:
        return result

    others: set[int] = set()  # tracks seen in the same frame as the target: other people
    last: Person | None = None
    reacquire_frames = cfg.reacquire_s * meta.fps
    max_step = cfg.skip * 2

    for f in frame_numbers:
        people = by_frame[f]
        mine = next((p for p in people if p.track_id == current), None)

        if mine is None and last is not None and last_frame_of[current] < f:
            # The target id is gone for good: look for the same person under a new id.
            candidates = [p for p in people if p.track_id not in others]
            taken: Person | None = None
            if f - last.frame_number <= reacquire_frames:
                overlaps = [(iou(p.bbox, last.bbox), -p.track_id, p) for p in candidates]
                overlaps = [o for o in overlaps if o[0] > cfg.reacquire_iou]
                if overlaps:
                    taken = max(overlaps, key=lambda o: (o[0], o[1]))[2]
            else:
                # Too late to match by position (they left and came back): re-select
                # among tracks that never shared a frame with the target.
                best = _best(_window_scores(by_frame, f, meta, cfg, others | {current}))
                taken = next((p for p in candidates if p.track_id == best), None)
            if taken is not None:
                result.handoffs.append((f, current, taken.track_id))
                current = taken.track_id
                mine = taken

        if mine is None:
            continue
        others.update(p.track_id for p in people if p.track_id != current)
        if mine.mean_conf < cfg.occlusion_confidence:
            continue  # too occluded to analyze; VIS-07 treats long runs as occlusion
        if (
            last is not None
            and f - last.frame_number <= max_step
            and iou(mine.bbox, last.bbox) < TELEPORT_IOU
        ):
            result.identity_switches += 1
        result.frames.append(_to_frame(mine))
        last = mine

    return result
