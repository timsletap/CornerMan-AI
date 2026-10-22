"""Privacy delete (PLT-10): find and remove every file derived from a video or session.

DB rows are removed by ON DELETE CASCADE; this module handles the files the rows point
to (or that the pipeline writes next to the original video by naming convention).
"""

import logging
from collections.abc import Iterable
from pathlib import Path

from app.config import settings
from app.models.analysis import AnalysisSession
from app.models.video import Video
from app.services.video import delete_video_file
from app.vision.types import poses_cache_path

logger = logging.getLogger(__name__)


def local_video_path(video: Video) -> Path:
    """Where a locally stored video lives (VIDEO_UPLOAD_DIR / key)."""
    return Path(settings.VIDEO_UPLOAD_DIR) / video.s3_key


def session_files(session: AnalysisSession, video_dir: Path | None) -> list[Path]:
    """Files written for one analysis session.

    Includes the annotated video and the intermediate h264 file left behind when a
    transcode fails. The poses cache belongs to the video (all its sessions share it),
    so it is removed with the video, not the session.
    """
    paths: list[Path] = []
    if session.annotated_video_path:
        paths.append(Path(session.annotated_video_path))
    dirs = {p.parent for p in paths}
    if video_dir is not None:
        dirs.add(video_dir)
    for d in dirs:
        paths += [d / f"{session.id}_annotated.mp4", d / f"{session.id}_annotated_h264.mp4"]
    return paths


def video_files(video: Video, sessions: Iterable[AnalysisSession]) -> list[Path]:
    """Local files for a video: the original, YouTube leftovers, the poses cache, and all
    session files."""
    sessions = list(sessions)
    paths: list[Path] = [Path(s.poses_cache_path) for s in sessions if s.poses_cache_path]
    video_dir: Path | None = None
    if settings.STORAGE_BACKEND == "local":
        original = local_video_path(video)
        video_dir = original.parent
        paths.append(original)
        if video.s3_url:
            paths.append(Path(video.s3_url))
        paths.append(original.with_name(f"{original.stem}_raw{original.suffix}"))
        paths.append(poses_cache_path(str(original)))
    for session in sessions:
        paths += session_files(session, video_dir)
    return paths


def remove_files(paths: Iterable[Path], context: str) -> int:
    """Delete local files, ignoring ones that don't exist. Returns how many were removed.

    Failures are logged, not raised: the DB rows are already gone and the caller should
    still get a success response.
    """
    removed = 0
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            resolved.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("privacy delete: could not remove %s (%s)", resolved, context)
    logger.info("privacy delete: removed %d file(s) for %s", removed, context)
    return removed


def remove_remote_original(video: Video) -> None:
    """Delete the original from S3 when that backend is in use."""
    if settings.STORAGE_BACKEND != "local":
        delete_video_file(video.s3_key)
