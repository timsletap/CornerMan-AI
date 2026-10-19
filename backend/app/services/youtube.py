"""YouTube scraping service - download UFC fight clips for analysis."""

import subprocess
import uuid
from pathlib import Path

import yt_dlp

from app.config import settings


def download_youtube_clip(
    url: str,
    user_id: uuid.UUID,
    max_duration: int | None = None,
) -> dict:
    """Download a YouTube video clip and save it locally for analysis.

    Args:
        url: YouTube video URL.
        user_id: User who initiated the download.
        max_duration: Max duration in seconds (defaults to MAX_VIDEO_DURATION_SECONDS).

    Returns:
        dict with keys: path, filename, duration, file_size_bytes, s3_key
    """
    if max_duration is None:
        max_duration = settings.MAX_VIDEO_DURATION_SECONDS

    video_id = str(uuid.uuid4())
    upload_dir = Path(settings.VIDEO_UPLOAD_DIR) / f"videos/{user_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    raw_path = upload_dir / f"{video_id}_raw.mp4"
    output_path = upload_dir / f"{video_id}.mp4"

    # Prefer h264 so OpenCV can decode it; fall back to anything available
    ydl_opts = {
        "format": (
            "bestvideo[vcodec^=avc1][height<=720]+bestaudio[acodec^=mp4a]/"
            "bestvideo[vcodec^=avc1][height<=720]+bestaudio/"
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/"
            "bestvideo+bestaudio/"
            "best"
        ),
        "outtmpl": str(raw_path),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "match_filter": yt_dlp.utils.match_filter_func(f"duration <= {max_duration}")
        if max_duration
        else None,
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise ValueError("Could not extract video info")

        title = info.get("title", "Unknown")
        duration = info.get("duration", 0)

        if duration and duration > max_duration:
            raw_path.unlink(missing_ok=True)
            raise ValueError(f"Video duration {duration}s exceeds {max_duration}s limit")

    # Always transcode to h264+aac so OpenCV can read it reliably
    _transcode_to_h264(raw_path, output_path)

    file_size = output_path.stat().st_size
    s3_key = f"videos/{user_id}/{video_id}.mp4"

    return {
        "path": str(output_path.resolve()),
        "filename": f"{title}.mp4",
        "duration": duration,
        "file_size_bytes": file_size,
        "s3_key": s3_key,
        "video_id": video_id,
    }


def _transcode_to_h264(src: Path, dst: Path) -> None:
    """Transcode video to h264/aac mp4 for OpenCV compatibility."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600)
    if result.returncode != 0:
        # Fall back: just rename raw file
        if not dst.exists():
            src.rename(dst)
        return

    # Clean up raw file
    src.unlink(missing_ok=True)


def search_youtube_clips(query: str, max_results: int = 10) -> list[dict]:
    """Search YouTube for fight clips matching a query.

    Returns list of dicts with: url, title, duration, thumbnail.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch",
    }

    search_query = f"ytsearch{max_results}:{query}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(search_query, download=False)
        if not result or "entries" not in result:
            return []

        clips = []
        for entry in result["entries"]:
            if entry is None:
                continue
            clips.append(
                {
                    "url": entry.get("url", ""),
                    "title": entry.get("title", ""),
                    "duration": entry.get("duration"),
                    "thumbnail": entry.get("thumbnails", [{}])[0].get("url")
                    if entry.get("thumbnails")
                    else None,
                    "channel": entry.get("channel", ""),
                }
            )

        return clips
