"""Provenance manifest: one JSON line per collected (or rejected) clip.

The manifest lives next to the clips (``eval/clips/manifest.jsonl``) and, like the
clips, is not committed. It records where each clip came from, under which license,
whom to credit, and why rejected clips were dropped, so they are not fetched again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_NAME = "manifest.jsonl"

Status = Literal["accepted", "rejected"]


class ClipRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_id: str
    status: Status
    source: str = Field(description="wikimedia, archive, youtube, or local")
    source_url: str
    title: str = ""
    creator: str = ""
    license: str | None = None
    license_url: str | None = None
    attribution: str = ""
    fighters: list[str] = Field(default=[], description="Consenting fighter ids (local)")
    file: str | None = Field(default=None, description="File name in the clips dir")
    sha256: str | None = None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    reject_reasons: list[str] = []
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Manifest:
    def __init__(self, clips_dir: Path) -> None:
        self.path = clips_dir / MANIFEST_NAME
        self.records: list[ClipRecord] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.records.append(ClipRecord.model_validate_json(line))

    def seen_url(self, url: str) -> bool:
        return any(r.source_url == url for r in self.records)

    def seen_sha(self, sha256: str) -> ClipRecord | None:
        return next(
            (r for r in self.records if r.sha256 == sha256 and r.status == "accepted"), None
        )

    def add(self, record: ClipRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        self.records.append(record)

    def accepted(self) -> list[ClipRecord]:
        return [r for r in self.records if r.status == "accepted"]


def credits_markdown(records: list[ClipRecord]) -> str:
    """Attribution list for accepted third-party clips (required by CC BY licenses)."""
    lines = ["# Clip credits", ""]
    for r in sorted(records, key=lambda r: r.clip_id):
        if r.source == "local":
            continue
        license_text = f"[{r.license}]({r.license_url})" if r.license_url else str(r.license)
        by = f" by {r.creator}" if r.creator else ""
        lines.append(
            f"- `{r.clip_id}`: [{r.title or r.source_url}]({r.source_url}){by}, {license_text}"
        )
    return "\n".join(lines) + "\n"
