"""Vision pipeline orchestration: stages, poses cache, progress, rendering, output JSON.

Stage 1 (``pose``) is the only expensive step; its output is cached next to the video
as ``<video stem>_poses.parquet`` and reused while the video, model, and frame skip are
unchanged. Stages 2 and 3 (``tracking``, ``signals``, ``strikes``, ``errors``) are pure
functions over the cached poses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.progress import update_progress
from app.vision import errors as error_stage
from app.vision import pose, render, strikes, tracking
from app.vision.signals import occluded_ranges
from app.vision.types import (
    ErrorDetection,
    FrameKeypoints,
    StrikeDetection,
    VideoMeta,
    VisionConfig,
    poses_cache_path,
)


@dataclass
class Analysis:
    """Stages 2 and 3 output for one video."""

    meta: VideoMeta
    frames: list[FrameKeypoints]
    occluded_ranges: list[tuple[int, int]]
    strikes: list[StrikeDetection]
    errors: list[ErrorDetection]

    @property
    def guard_score(self) -> float:
        return error_stage.guard_score(self.strikes, self.errors)


def analyze_poses(poses: pose.Poses, cfg: VisionConfig) -> Analysis:
    """Stages 2 and 3 on cached poses. No model, I/O, or progress reporting."""
    meta = poses.meta
    frames = tracking.primary_track(poses.frames, meta, cfg)
    ranges, active = occluded_ranges(frames, meta, cfg)
    found = strikes.detect_strikes(frames, active, meta, cfg)
    errs = error_stage.analyze_guard(found, frames, cfg) + error_stage.detect_telegraph(
        found, frames, cfg
    )
    return Analysis(meta, frames, ranges, found, errs)


def load_or_extract_poses(video_path: str, cfg: VisionConfig, session: str) -> pose.Poses:
    cache = poses_cache_path(video_path)
    cached = pose.read_poses(cache, cfg, pose.probe_meta(video_path))
    if cached is not None:
        return cached

    def report(frame_num: int, total: int) -> None:
        update_progress(
            session,
            "pose_extraction",
            frame_num / max(1, total) * 0.6,  # pose extraction is 0-60% of total
            f"Tracking poses: frame {frame_num}/{total}",
        )

    poses = pose.extract_poses(video_path, cfg, report)
    pose.write_poses(poses, cache, cfg)
    return poses


def build_output_json(
    session_id: uuid.UUID,
    analysis: Analysis,
    annotated_video_path: str | None,
    poses_path: Path | None,
) -> dict[str, Any]:
    """VIS-05: structured output JSON."""
    meta = analysis.meta
    found = analysis.strikes
    errs = analysis.errors
    avg_velocity = sum(s.velocity for s in found) / len(found) if found else 0.0
    duration_sec = meta.total_frames / meta.fps if meta.fps > 0 else 0

    return {
        "session_id": str(session_id),
        "video_metadata": {
            "fps": meta.fps,
            "total_frames": meta.total_frames,
            "duration_seconds": round(duration_sec, 2),
            "resolution": {"width": meta.width, "height": meta.height},
        },
        "frames_analyzed": len(analysis.frames),
        "primary_actor_detected": len(analysis.frames) > 0,
        "occluded_ranges": [
            {
                "start_frame": s,
                "end_frame": e,
                "start_ms": int(s / meta.fps * 1000),
                "end_ms": int(e / meta.fps * 1000),
            }
            for s, e in analysis.occluded_ranges
        ],
        "strike_events": [
            {
                "frame_number": s.frame_number,
                "timestamp_ms": s.timestamp_ms,
                "hand": s.hand,
                "strike_type": s.strike_type,
                "velocity": round(s.velocity, 2),
                "wrist_position": {
                    "x": round(s.wrist_position[0], 1),
                    "y": round(s.wrist_position[1], 1),
                },
                "keypoints": s.keypoints_snapshot,
            }
            for s in found
        ],
        "error_flags": [
            {
                "frame_number": e.frame_number,
                "timestamp_ms": e.timestamp_ms,
                "error_type": e.error_type,
                "severity": e.severity,
                "details": e.details,
                "related_strike_index": e.related_strike_index,
            }
            for e in errs
        ],
        "metrics": {
            "total_strikes": len(found),
            "avg_velocity": round(avg_velocity, 2),
            "guard_score": analysis.guard_score,
            "strikes_per_minute": round(len(found) / max(1, duration_sec / 60), 1),
            "error_counts": {
                "dropped_guard": sum(1 for e in errs if e.error_type == "dropped_guard"),
                "chicken_wing": sum(1 for e in errs if e.error_type == "chicken_wing"),
            },
        },
        "annotated_video_path": annotated_video_path,
        "poses_cache_path": str(poses_path) if poses_path else None,
    }


def run_vision_analysis(video_path: str, session_id: uuid.UUID) -> dict[str, Any]:
    """Run the full vision pipeline on a video file. Called from Celery (sync)."""
    cfg = VisionConfig.from_settings()
    sid = str(session_id)

    poses = load_or_extract_poses(video_path, cfg, sid)

    update_progress(sid, "strike_detection", 0.65, "Detecting strikes from velocity data...")
    analysis = analyze_poses(poses, cfg)
    update_progress(sid, "guard_analysis", 0.70, "Analyzing guard integrity...")
    update_progress(sid, "telegraph_detection", 0.75, "Detecting telegraph patterns...")

    update_progress(sid, "rendering", 0.78, "Rendering annotated video with tracking overlay...")

    def report(frame_num: int, total: int) -> None:
        update_progress(
            sid,
            "rendering",
            0.78 + (frame_num / max(1, total)) * 0.12,
            f"Rendering frame {frame_num}/{total}",
        )

    annotated = render.render_annotated(
        video_path,
        str(Path(video_path).parent / f"{session_id}_annotated.mp4"),
        analysis.meta,
        analysis.frames,
        analysis.strikes,
        analysis.errors,
        analysis.guard_score,
        report,
    )
    return build_output_json(session_id, analysis, annotated, poses_cache_path(video_path))
