"""Search clients for openly licensed video sources.

Each source returns ``Candidate`` objects with the license as the source reports it;
the caller decides with ``licenses.check`` what to keep. Network access goes through
an ``httpx.Client`` passed in, so tests can use ``httpx.MockTransport``.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from tools.collect import licenses

USER_AGENT = "CornerMan-AI-clip-collector/1.0 (https://github.com/timsletap/CornerMan-AI)"

VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".mkv", ".m4v"}


@dataclass(frozen=True)
class Candidate:
    source: str
    source_url: str
    """Human-facing page for the clip (credited in attributions)."""
    download_url: str | None
    """Direct file URL; None when a downloader such as yt-dlp resolves it."""
    title: str
    creator: str
    license_raw: str
    license_url: str | None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None

    @property
    def license_id(self) -> str | None:
        return licenses.normalize(self.license_url) or licenses.normalize(self.license_raw)

    @property
    def attribution(self) -> str:
        by = f" by {self.creator}" if self.creator else ""
        return f'"{self.title}"{by}, {self.license_id or self.license_raw}, {self.source_url}'


class Source(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[Candidate]: ...


def _strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _meta(ext: dict[str, Any], key: str) -> str:
    value = ext.get(key, {}).get("value", "")
    return _strip_html(str(value))


class WikimediaSource:
    """Wikimedia Commons video files (search in the File namespace)."""

    name = "wikimedia"
    API = "https://commons.wikimedia.org/w/api.php"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def search(self, query: str, limit: int) -> list[Candidate]:
        params: dict[str, str | int] = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:video",
            "gsrnamespace": 6,
            "gsrlimit": min(limit, 50),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        }
        res = self.client.get(self.API, params=params)
        res.raise_for_status()
        pages = res.json().get("query", {}).get("pages", {})
        out: list[Candidate] = []
        for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            info = (page.get("imageinfo") or [{}])[0]
            if not str(info.get("mime", "")).startswith("video/"):
                continue
            ext = info.get("extmetadata", {})
            out.append(
                Candidate(
                    source=self.name,
                    source_url=info.get("descriptionurl", ""),
                    download_url=info.get("url"),
                    title=str(page.get("title", "")).removeprefix("File:"),
                    creator=_meta(ext, "Artist"),
                    license_raw=_meta(ext, "LicenseShortName"),
                    license_url=_meta(ext, "LicenseUrl") or None,
                    duration_s=info.get("duration"),
                    width=info.get("width"),
                    height=info.get("height"),
                )
            )
        return out[:limit]


class ArchiveSource:
    """Internet Archive movies whose license URL is Creative Commons or public domain."""

    name = "archive"
    SEARCH = "https://archive.org/advancedsearch.php"
    METADATA = "https://archive.org/metadata/{identifier}"
    DOWNLOAD = "https://archive.org/download/{identifier}/{name}"
    DETAILS = "https://archive.org/details/{identifier}"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def search(self, query: str, limit: int) -> list[Candidate]:
        q = (
            f"({query}) AND mediatype:(movies) AND "
            "licenseurl:(*creativecommons.org* OR *publicdomain*)"
        )
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("q", q),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("fl[]", "creator"),
            ("fl[]", "licenseurl"),
            ("rows", min(limit, 100)),
            ("output", "json"),
        ]
        res = self.client.get(self.SEARCH, params=params)
        res.raise_for_status()
        out: list[Candidate] = []
        for doc in res.json().get("response", {}).get("docs", []):
            identifier = doc["identifier"]
            video = self._best_file(identifier)
            if video is None:
                continue
            creator = doc.get("creator", "")
            out.append(
                Candidate(
                    source=self.name,
                    source_url=self.DETAILS.format(identifier=identifier),
                    download_url=self.DOWNLOAD.format(identifier=identifier, name=video["name"]),
                    title=str(doc.get("title", identifier)),
                    creator=", ".join(creator) if isinstance(creator, list) else str(creator),
                    license_raw=str(doc.get("licenseurl", "")),
                    license_url=doc.get("licenseurl"),
                    duration_s=_float(video.get("length")),
                    width=_int(video.get("width")),
                    height=_int(video.get("height")),
                )
            )
        return out[:limit]

    def _best_file(self, identifier: str) -> dict[str, Any] | None:
        """The largest original MP4/WebM in an item, if any."""
        res = self.client.get(self.METADATA.format(identifier=identifier))
        res.raise_for_status()
        files = [
            f
            for f in res.json().get("files", [])
            if any(str(f.get("name", "")).lower().endswith(e) for e in (".mp4", ".webm"))
        ]
        if not files:
            return None
        originals = [f for f in files if f.get("source") == "original"] or files
        best: dict[str, Any] = max(originals, key=lambda f: _int(f.get("size")) or 0)
        return best


class YouTubeSource:
    """YouTube search restricted to Creative Commons (CC BY 3.0) videos.

    Needs a YouTube Data API key. Downloading is done with yt-dlp; note that YouTube's
    Terms of Service restrict downloading even for CC-licensed videos, so check that
    your use is acceptable before fetching from this source.
    """

    name = "youtube"
    SEARCH = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
    CC_BY_URL = "https://creativecommons.org/licenses/by/3.0/legalcode"

    def __init__(self, client: httpx.Client, api_key: str) -> None:
        if not api_key:
            raise ValueError("YouTube source needs YOUTUBE_API_KEY")
        self.client = client
        self.api_key = api_key

    def search(self, query: str, limit: int) -> list[Candidate]:
        res = self.client.get(
            self.SEARCH,
            params={
                "part": "id",
                "q": query,
                "type": "video",
                "videoLicense": "creativeCommon",
                "maxResults": min(limit, 50),
                "key": self.api_key,
            },
        )
        res.raise_for_status()
        ids = [item["id"]["videoId"] for item in res.json().get("items", [])]
        if not ids:
            return []
        res = self.client.get(
            self.VIDEOS,
            params={"part": "snippet,status", "id": ",".join(ids), "key": self.api_key},
        )
        res.raise_for_status()
        out: list[Candidate] = []
        for item in res.json().get("items", []):
            # Re-check: search filters can be stale; the video's own status is authoritative.
            if item.get("status", {}).get("license") != "creativeCommon":
                continue
            snippet = item.get("snippet", {})
            out.append(
                Candidate(
                    source=self.name,
                    source_url=f"https://www.youtube.com/watch?v={item['id']}",
                    download_url=None,
                    title=snippet.get("title", ""),
                    creator=snippet.get("channelTitle", ""),
                    license_raw="CC BY 3.0",
                    license_url=self.CC_BY_URL,
                )
            )
        return out[:limit]


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        if isinstance(value, str) and ":" in value:  # archive.org "MM:SS" or "HH:MM:SS"
            total = 0.0
            for part in value.split(":"):
                total = total * 60 + float(part)
            return total
        return None
