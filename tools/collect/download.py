"""Download a candidate to a file, with a size cap and a SHA-256 of the bytes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from tools.collect.sources import VIDEO_EXTENSIONS, Candidate

CHUNK_BYTES = 1 << 20


class DownloadError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def extension_for(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in VIDEO_EXTENSIONS else ".mp4"


def http_download(client: httpx.Client, url: str, dest_dir: Path, max_bytes: int) -> Path:
    """Stream ``url`` into a temp file in ``dest_dir``; raises DownloadError over max_bytes."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest_dir, suffix=extension_for(url) + ".part")
    path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as f, client.stream("GET", url, follow_redirects=True) as res:
            res.raise_for_status()
            size = 0
            for chunk in res.iter_bytes(CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise DownloadError(f"larger than {max_bytes // (1 << 20)} MB")
                f.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def ytdlp_download(url: str, dest_dir: Path, max_bytes: int) -> Path:
    """Download a YouTube video (best MP4 up to 1080p) with yt-dlp."""
    import yt_dlp

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=dest_dir, prefix="ytdlp-"))
    opts = {
        "format": "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(tmp_dir / "clip.%(ext)s"),
        "max_filesize": max_bytes,
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [p for p in tmp_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS]
    if not files:
        raise DownloadError("yt-dlp produced no video file")
    final = dest_dir / f"{tmp_dir.name}{files[0].suffix}.part"
    files[0].replace(final)
    for leftover in tmp_dir.iterdir():
        leftover.unlink()
    tmp_dir.rmdir()
    return final


def fetch(candidate: Candidate, client: httpx.Client, dest_dir: Path, max_bytes: int) -> Path:
    if candidate.download_url:
        return http_download(client, candidate.download_url, dest_dir, max_bytes)
    if candidate.source == "youtube":
        return ytdlp_download(candidate.source_url, dest_dir, max_bytes)
    raise DownloadError(f"no download method for {candidate.source}")
