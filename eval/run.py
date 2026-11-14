"""Run the vision pipeline on a labeled split and write the metrics report (EVAL-04).

Usage (from the repo root):
    python -m eval.run --split dev|test|fixtures [--window-ms 150] [--from-cache] [--out FILE]
    python -m eval.run --split dir --labels-dir DIR [--clips-dir DIR] [--name NAME]

For each clip in the split the harness loads ``eval/labels/<clip_id>.json``, gets poses
(from ``eval/clips/<clip_id>_poses.parquet`` when it is valid, else by running the pose
model on ``eval/clips/<clip_id>.<ext>``), runs stages 2 and 3, and matches predictions
to labels. The report (FRD section 6.6) is printed and written to
``eval/reports/<git_sha>_<split>.json``.

``--split fixtures`` scores the committed poses and labels in ``tests/fixtures/eval/``
(no video needed); CI uses it as the regression gate (EVAL-05).

Never tune thresholds on the test split.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.vision import pose
from app.vision.pipeline import Analysis, analyze_poses
from app.vision.types import VisionConfig, poses_cache_path
from eval import metrics
from eval.match import DEFAULT_WINDOW_MS
from eval.metrics import ClipScore, PredError, PredStrike
from eval.report import IdentitySwitches, Report, Throughput
from eval.schema import ClipLabels, load_labels, load_splits

ROOT = Path(__file__).resolve().parents[1]
LABELS_DIR = ROOT / "eval" / "labels"
CLIPS_DIR = ROOT / "eval" / "clips"
SPLITS = ROOT / "eval" / "splits.yaml"
REPORTS_DIR = ROOT / "eval" / "reports"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "eval"
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".mkv", ".m4v"}


class EvalError(Exception):
    """A problem with the eval inputs (missing clips, labels, or poses)."""


@dataclasses.dataclass
class ClipRun:
    labels: ClipLabels
    analysis: Analysis
    strikes: list[PredStrike]
    errors: list[PredError]
    score: ClipScore
    video_seconds: float
    stage1_seconds: float | None
    """Wall-clock seconds of pose inference; None when poses came from the cache."""
    stages23_seconds: float


def predictions(analysis: Analysis) -> tuple[list[PredStrike], list[PredError]]:
    """Pipeline output in the label vocabulary (times in ms, anatomical hands)."""
    strikes = [
        PredStrike(
            t_ms=s.timestamp_ms,
            hand=s.hand,
            type=s.strike_type,
        )
        for s in analysis.strikes
    ]
    errors = []
    for e in analysis.errors:
        # dropped_guard is labeled with the hand that dropped; chicken_wing with the puncher.
        hand = e.details.get("off_hand") or e.details.get("hand")
        if hand is None:
            continue
        errors.append(
            PredError(
                t_ms=e.timestamp_ms,
                hand=str(hand),
                type=e.error_type,
            )
        )
    return strikes, errors


def find_video(clips_dir: Path, clip_id: str) -> Path | None:
    for path in sorted(clips_dir.glob(f"{clip_id}.*")):
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return path
    return None


def load_poses(
    clip_id: str, clips_dir: Path, cfg: VisionConfig, from_cache: bool
) -> tuple[pose.Poses, float | None]:
    """Poses for a clip and the seconds spent on pose inference (None if cached)."""
    video = find_video(clips_dir, clip_id)
    cache = poses_cache_path(str(clips_dir / f"{clip_id}.mp4"))
    if video is not None:
        cached = pose.read_poses(cache, cfg, pose.probe_meta(str(video)))
        if cached is not None:
            return cached, None
        if not from_cache:
            start = time.perf_counter()
            poses = pose.extract_poses(str(video), cfg)
            elapsed = time.perf_counter() - start
            pose.write_poses(poses, cache, cfg)
            return poses, elapsed
    if cache.exists():
        return pose.read_poses_file(cache), None
    raise EvalError(
        f"{clip_id}: no usable poses ({cache.name}) "
        + ("and --from-cache was given" if video is not None else f"and no video in {clips_dir}")
    )


def run_clip(
    clip_id: str,
    labels_dir: Path,
    clips_dir: Path,
    cfg: VisionConfig,
    window_ms: int,
    from_cache: bool,
) -> ClipRun:
    label_file = labels_dir / f"{clip_id}.json"
    if not label_file.exists():
        raise EvalError(f"{clip_id}: no label file at {label_file}")
    labels = load_labels(label_file)
    poses, stage1 = load_poses(clip_id, clips_dir, cfg, from_cache)

    start = time.perf_counter()
    # The label's stance stands in for the fighter's profile, as in the app.
    analysis = analyze_poses(poses, cfg, profile_stance=labels.fighter.stance)
    stages23 = time.perf_counter() - start

    strikes, errors = predictions(analysis)
    meta = poses.meta
    return ClipRun(
        labels=labels,
        analysis=analysis,
        strikes=strikes,
        errors=errors,
        score=metrics.score_clip(labels, strikes, errors, window_ms),
        video_seconds=meta.total_frames / meta.fps if meta.fps > 0 else 0.0,
        stage1_seconds=stage1,
        stages23_seconds=stages23,
    )


def git_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    return out.stdout.strip() or "unknown"


def hardware() -> str:
    cpu = platform.processor() or platform.machine()
    device = "CPU only"
    try:
        import torch

        if torch.cuda.is_available():
            device = str(torch.cuda.get_device_name(0))
    except ImportError:
        pass
    return f"{cpu}, {os.cpu_count()} logical cores, {device}"


def config_hash(cfg: VisionConfig) -> str:
    payload = json.dumps(dataclasses.asdict(cfg), sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _x_realtime(video_seconds: float, wall_seconds: float) -> float | None:
    return round(video_seconds / wall_seconds, 2) if wall_seconds > 0 else None


def build_report(split: str, runs: Sequence[ClipRun], cfg: VisionConfig, window_ms: int) -> Report:
    scores = [r.score for r in runs]
    inferred = [r for r in runs if r.stage1_seconds is not None]
    return Report(
        git_sha=git_sha(),
        split=split,
        created_at=datetime.now(UTC).replace(microsecond=0),
        config_hash=config_hash(cfg),
        match_window_ms=window_ms,
        clips=[r.labels.clip_id for r in runs],
        detection=metrics.detection(scores),
        strike_type=metrics.strike_type(scores),
        errors=metrics.errors(scores),
        identity_switches=IdentitySwitches(
            total=sum(r.analysis.identity_switches for r in runs),
            per_clip={r.labels.clip_id: r.analysis.identity_switches for r in runs},
        ),
        throughput=Throughput(
            stage1_x_realtime=_x_realtime(
                sum(r.video_seconds for r in inferred),
                sum(r.stage1_seconds or 0.0 for r in inferred),
            ),
            stages23_x_realtime=_x_realtime(
                sum(r.video_seconds for r in runs), sum(r.stages23_seconds for r in runs)
            ),
            hardware=hardware(),
        ),
        by_tag=metrics.by_tag(scores),
    )


def split_clips(split: str, splits_file: Path) -> tuple[list[str], Path, Path]:
    """Clip ids, labels dir, and clips dir for a split name."""
    if split == "fixtures":
        ids = sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))
        return ids, FIXTURES_DIR, FIXTURES_DIR
    splits = load_splits(splits_file)
    ids = list(splits.dev if split == "dev" else splits.test)
    return ids, LABELS_DIR, CLIPS_DIR


def evaluate(
    split: str,
    clip_ids: Sequence[str],
    labels_dir: Path,
    clips_dir: Path,
    cfg: VisionConfig,
    window_ms: int = DEFAULT_WINDOW_MS,
    from_cache: bool = False,
) -> tuple[Report, list[ClipRun]]:
    if not clip_ids:
        raise EvalError(
            f"split {split!r} has no clips: label clips (eval/LABELING.md) and list them "
            "in eval/splits.yaml"
        )
    runs = [run_clip(c, labels_dir, clips_dir, cfg, window_ms, from_cache) for c in clip_ids]
    return build_report(split, runs, cfg, window_ms), runs


def format_report(report: Report) -> str:
    d = report.detection
    lines = [
        f"split {report.split}  clips {len(report.clips)}  sha {report.git_sha}  "
        f"window ±{report.match_window_ms} ms",
        "",
        f"{'':<16}{'P':>8}{'R':>8}{'F1':>8}{'TP':>6}{'FP':>6}{'FN':>6}",
        f"{'strikes':<16}{d.precision:>8.3f}{d.recall:>8.3f}{d.f1:>8.3f}"
        f"{d.tp:>6}{d.fp:>6}{d.fn:>6}",
    ]
    for name, e in report.errors.items():
        lines.append(
            f"{name:<16}{e.precision:>8.3f}{e.recall:>8.3f}{e.f1:>8.3f}{e.tp:>6}{e.fp:>6}{e.fn:>6}"
        )
    lines += ["", f"strike type macro-F1 {report.strike_type.macro_f1:.3f} (matched pairs)"]
    for name, c in report.strike_type.per_class.items():
        lines.append(f"  {name:<14}{c.precision:>8.3f}{c.recall:>8.3f}{c.f1:>8.3f}   n={c.support}")
    if report.identity_switches is not None:
        lines += ["", f"identity switches {report.identity_switches.total}"]
    if report.by_tag:
        lines += ["", "detection F1 by tag"]
        lines += [
            f"  {tag:<14}{t.detection_f1:>8.3f}   clips={t.clips}"
            for tag, t in report.by_tag.items()
        ]
    t = report.throughput
    lines += [
        "",
        f"throughput: stage 1 {t.stage1_x_realtime or 'cached'} x real time, "
        f"stages 2-3 {t.stages23_x_realtime} x real time ({t.hardware})",
    ]
    return "\n".join(lines)


def write_report(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run", description=__doc__)
    parser.add_argument("--split", choices=["dev", "test", "fixtures", "dir"], required=True)
    parser.add_argument(
        "--labels-dir", type=Path, default=None, help="with --split dir: every *.json here"
    )
    parser.add_argument(
        "--clips-dir", type=Path, default=None, help="with --split dir: videos and pose caches"
    )
    parser.add_argument("--name", default=None, help="split name written in the report")
    parser.add_argument("--window-ms", type=int, default=DEFAULT_WINDOW_MS)
    parser.add_argument("--from-cache", action="store_true", help="never run the pose model")
    parser.add_argument("--splits", type=Path, default=SPLITS)
    parser.add_argument("--out", type=Path, default=None, help="report path")
    args = parser.parse_args(argv)

    cfg = VisionConfig.from_settings()
    try:
        if args.split == "dir":
            if args.labels_dir is None:
                raise EvalError("--split dir needs --labels-dir")
            labels_dir = args.labels_dir
            clips_dir = args.clips_dir or labels_dir
            clip_ids = sorted(p.stem for p in labels_dir.glob("*.json"))
        else:
            clip_ids, labels_dir, clips_dir = split_clips(args.split, args.splits)
        name = args.name or args.split
        report, _ = evaluate(
            name, clip_ids, labels_dir, clips_dir, cfg, args.window_ms, args.from_cache
        )
    except EvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(format_report(report))
    out = args.out or REPORTS_DIR / f"{report.git_sha}_{name}.json"
    write_report(report, out)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
