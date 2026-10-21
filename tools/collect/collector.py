"""Collect clips into the eval clips dir: license check, download, quality gates, manifest."""

from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from tools.collect import licenses, quality
from tools.collect.download import DownloadError, fetch, sha256_file
from tools.collect.manifest import ClipRecord, Manifest
from tools.collect.sources import VIDEO_EXTENSIONS, Candidate, Source

DEFAULT_MAX_MB = 500

PersonCheck = Callable[[Path], float]


@dataclass
class Settings:
    clips_dir: Path
    rules: quality.QualityRules = field(default_factory=quality.QualityRules)
    allow_nc: bool = False
    max_bytes: int = DEFAULT_MAX_MB << 20
    person_check: PersonCheck | None = None


@dataclass
class Summary:
    accepted: list[ClipRecord] = field(default_factory=list)
    rejected: list[ClipRecord] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    """Human-readable reasons for candidates not downloaded (license, duplicate, error)."""


def slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:max_len].rstrip("_") or "clip"


def _clip_id(source: str, title: str, sha256: str) -> str:
    return f"{source}_{slug(Path(title).stem)}_{sha256[:8]}"


def ingest_file(
    tmp: Path,
    record: ClipRecord,
    manifest: Manifest,
    settings: Settings,
) -> ClipRecord | None:
    """Gate a downloaded/copied temp file and file it under the clips dir.

    Returns the manifest record, or None for a duplicate of an accepted clip. The temp
    file is always consumed (moved or deleted).
    """
    try:
        sha = sha256_file(tmp)
        if manifest.seen_sha(sha):
            return None
        record.sha256 = sha
        record.clip_id = _clip_id(record.source, record.title or tmp.stem, sha)
        try:
            info = quality.probe(tmp)
            cuts = quality.detect_cuts(tmp)
            people = settings.person_check(tmp) if settings.person_check else None
            reasons = quality.check_rules(info, cuts, settings.rules, people)
            record.width, record.height = info.width, info.height
            record.fps, record.duration_s = round(info.fps, 3), round(info.duration_s, 3)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            reasons = [f"unreadable video: {exc}"]

        if reasons:
            record.status = "rejected"
            record.reject_reasons = reasons
        else:
            suffix = tmp.name.removesuffix(".part")
            ext = Path(suffix).suffix.lower() if Path(suffix).suffix else ".mp4"
            final = settings.clips_dir / f"{record.clip_id}{ext}"
            settings.clips_dir.mkdir(parents=True, exist_ok=True)
            tmp.replace(final)
            record.status = "accepted"
            record.file = final.name
        manifest.add(record)
        return record
    finally:
        tmp.unlink(missing_ok=True)


def _record_for(c: Candidate, license_id: str) -> ClipRecord:
    return ClipRecord(
        clip_id="pending",
        status="rejected",
        source=c.source,
        source_url=c.source_url,
        title=c.title,
        creator=c.creator,
        license=license_id,
        license_url=c.license_url,
        attribution=c.attribution,
    )


def collect_from_source(
    source: Source,
    client: httpx.Client,
    query: str,
    limit: int,
    settings: Settings,
    log: Callable[[str], None] = print,
) -> Summary:
    """Search one source and ingest every candidate that passes the license policy."""
    manifest = Manifest(settings.clips_dir)
    summary = Summary()
    staging = settings.clips_dir / ".staging"
    for c in source.search(query, limit):
        decision = licenses.check(c.license_id, settings.allow_nc)
        if not decision.allowed:
            summary.skipped.append(f"{c.source_url}: {decision.reason}")
            continue
        if manifest.seen_url(c.source_url):
            summary.skipped.append(f"{c.source_url}: already in manifest")
            continue
        if c.height is not None and c.height < settings.rules.min_height:
            summary.skipped.append(f"{c.source_url}: height {c.height}px too small")
            continue
        log(f"downloading {c.title} ({decision.reason})")
        try:
            tmp = fetch(c, client, staging, settings.max_bytes)
        except (DownloadError, httpx.HTTPError) as exc:
            summary.skipped.append(f"{c.source_url}: download failed: {exc}")
            continue
        assert c.license_id is not None
        record = ingest_file(tmp, _record_for(c, c.license_id), manifest, settings)
        _tally(summary, record, c.source_url)
    shutil.rmtree(staging, ignore_errors=True)
    return summary


def _tally(summary: Summary, record: ClipRecord | None, where: str) -> None:
    if record is None:
        summary.skipped.append(f"{where}: duplicate of an accepted clip")
    elif record.status == "accepted":
        summary.accepted.append(record)
    else:
        summary.rejected.append(record)


class FighterConsent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent: bool = Field(description="Fighter agreed to recording and use for training/eval")
    date: dt.date | None = None
    notes: str = ""


class ConsentFile(BaseModel):
    """Consent sheet for owner-recorded footage (``consent.yaml`` next to the clips).

    Fighter ids are anonymous (``f01``); do not put names here.
    """

    model_config = ConfigDict(extra="forbid")

    recorded_by: str = Field(min_length=1)
    fighters: dict[str, FighterConsent]
    clips: dict[str, list[str]] = Field(description="file name -> fighter ids in the clip")


def load_consent(path: Path) -> ConsentFile:
    return ConsentFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def consent_problems(consent: ConsentFile, filename: str) -> list[str]:
    fighters = consent.clips.get(filename)
    if fighters is None:
        return [f"{filename} is not listed under clips in the consent file"]
    if not fighters:
        return [f"{filename} lists no fighters"]
    problems = []
    for fid in fighters:
        entry = consent.fighters.get(fid)
        if entry is None:
            problems.append(f"fighter {fid} has no consent entry")
        elif not entry.consent:
            problems.append(f"fighter {fid} has not consented")
    return problems


def collect_local(folder: Path, consent_path: Path, settings: Settings) -> Summary:
    """Copy owner-recorded clips with full consent into the clips dir (originals untouched)."""
    consent = load_consent(consent_path)
    manifest = Manifest(settings.clips_dir)
    summary = Summary()
    staging = settings.clips_dir / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        problems = consent_problems(consent, path.name)
        if problems:
            summary.skipped.append(f"{path.name}: " + "; ".join(problems))
            continue
        url = path.resolve().as_uri()
        tmp = staging / f"{path.stem}{path.suffix.lower()}.part"
        shutil.copy2(path, tmp)
        record = ClipRecord(
            clip_id="pending",
            status="rejected",
            source="local",
            source_url=url,
            title=path.name,
            creator=consent.recorded_by,
            license=licenses.OWN,
            fighters=consent.clips[path.name],
        )
        _tally(summary, ingest_file(tmp, record, manifest, settings), path.name)
    shutil.rmtree(staging, ignore_errors=True)
    return summary
