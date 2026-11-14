"""BoxingVI (arXiv 2511.16524) as an eval set for strike detection and strike type.

The dataset publishes punch annotations (start frame, end frame, one of six classes) and
YouTube links, not video files. This module turns one video's annotations into the
project's label format and cuts the matching excerpt, so ``python -m eval.run`` can
score it:

    python -m eval.public_sets.boxingvi convert --annotations <dir of V*.xlsx> \
        --videos <dir of V*.mp4> --out <dir> [--max-seconds 180]
    python -m eval.run --split dir --labels-dir <out> --clips-dir <out>

What the labels can and cannot measure:
- Detection and strike type: yes. ``t_ms`` is the middle of the annotated punch, which
  stands in for full extension (punches are 0.2 to 0.6 s long, the match window is 150 ms).
- Lead or rear hand: the dataset says lead/rear, the project labels left/right, and the
  dataset gives no stance. Stance comes from ``--stance V1=southpaw`` or defaults to
  orthodox. Until someone has checked each video, hand agreement is not trustworthy.
- Target (head or body), technique errors, landed or missed: not labeled. ``target`` is
  written as ``head`` because the schema needs a value; ignore error metrics on this set.
- Gaps of more than ``GAP_SECONDS`` between annotated punches are marked as skipped:
  the dataset does not say whether nothing happened there or nobody labeled it.

License: the repository states none. Use the data for local measurement only; do not
commit videos, excerpts, or labels derived from it, and do not train a shipped model on
it without the owner's decision (FRD Section 22.1).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.schema import ClipLabels, Fighter, SkippedSpan, Stance, StrikeLabel

GAP_SECONDS = 10.0
"""A silence longer than this between labeled punches is treated as unlabeled."""

# BoxingVI class -> (project strike type, lead hand?)
CLASSES: dict[str, tuple[str, bool]] = {
    "jab": ("jab", True),
    "cross": ("cross", False),
    "lead hook": ("hook", True),
    "rear hook": ("hook", False),
    "lead uppercut": ("uppercut", True),
    "rear uppercut": ("uppercut", False),
}


@dataclass(frozen=True)
class Punch:
    start_frame: int
    end_frame: int
    strike_type: str
    lead: bool


def parse_rows(rows: Sequence[Sequence[Any]]) -> list[Punch]:
    """Punches from a sheet's rows.

    The ten published sheets have ten layouts. What they share: the class name is a
    text cell, and the first two numbers before it are the start and end frame.
    """
    punches: list[Punch] = []
    for row in rows:
        for i, cell in enumerate(row):
            key = cell.strip().lower() if isinstance(cell, str) else None
            if key not in CLASSES:
                continue
            numbers = [
                int(v)
                for v in row[:i]
                if isinstance(v, int | float) and not isinstance(v, bool) and v == v
            ]
            if len(numbers) >= 2 and numbers[1] >= numbers[0]:
                strike_type, lead = CLASSES[key]
                punches.append(Punch(numbers[0], numbers[1], strike_type, lead))
            break
    return sorted(punches, key=lambda p: p.start_frame)


def read_sheet(path: Path) -> list[Punch]:
    from openpyxl import load_workbook

    sheet = load_workbook(path, read_only=True, data_only=True).active
    return parse_rows([list(r) for r in sheet.iter_rows(values_only=True)])


def window(punches: Sequence[Punch], fps: float, max_seconds: float | None) -> list[Punch]:
    """The punches in the first ``max_seconds`` of annotated footage (all when None)."""
    if not punches or max_seconds is None:
        return list(punches)
    last = punches[0].start_frame + int(max_seconds * fps)
    return [p for p in punches if p.end_frame <= last]


def to_labels(
    clip_id: str,
    punches: Sequence[Punch],
    fps: float,
    stance: Stance,
    first_frame: int,
    pad_frames: int,
) -> ClipLabels:
    """Labels for an excerpt that starts ``pad_frames`` before ``first_frame``.

    Times are ms from the start of the excerpt. ``fps`` is the video's frame rate.
    """
    origin = first_frame - pad_frames

    def ms(frame: float) -> int:
        return max(0, round((frame - origin) / fps * 1000))

    lead_hand = "left" if stance == "orthodox" else "right"
    rear_hand = "right" if stance == "orthodox" else "left"
    strikes = [
        StrikeLabel(
            t_ms=ms((p.start_frame + p.end_frame) / 2),
            hand=lead_hand if p.lead else rear_hand,  # type: ignore[arg-type]
            type=p.strike_type,  # type: ignore[arg-type]
            target="head",
        )
        for p in punches
    ]
    strikes.sort(key=lambda s: s.t_ms)
    skipped = [
        SkippedSpan(
            start_ms=ms(a.end_frame + fps),
            end_ms=ms(b.start_frame - fps),
            reason=f"no annotations for more than {GAP_SECONDS:.0f} s",
        )
        for a, b in zip(punches, punches[1:], strict=False)
        if (b.start_frame - a.end_frame) / fps > GAP_SECONDS
    ]
    return ClipLabels(
        clip_id=clip_id,
        fps=fps,
        tags=[],
        fighter=Fighter(stance=stance, track_hint="the boxer BoxingVI annotated"),
        strikes=strikes,
        notes=skipped,
        labeler="boxingvi",
        label_version=1,
    )


def probe_fps(video: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def cut_excerpt(video: Path, out: Path, start_s: float, duration_s: float) -> None:
    """Re-encode ``duration_s`` seconds from ``start_s`` (frame-accurate, no audio)."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-ss", f"{start_s:.3f}", "-i", str(video),
            "-t", f"{duration_s:.3f}", "-an", "-c:v", "libx264", "-crf", "18",
            "-preset", "veryfast", str(out),
        ],
        check=True,
    )  # fmt: skip


def convert(
    annotations: Path,
    videos: Path,
    out: Path,
    stances: dict[str, Stance],
    max_seconds: float | None,
    pad_seconds: float = 2.0,
) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for sheet in sorted(annotations.glob("V*.xlsx"), key=lambda p: int(p.stem[1:])):
        name = sheet.stem
        video = next(iter(sorted(videos.glob(f"{name}.*"))), None)
        if video is None:
            print(f"{name}: no video, skipped")
            continue
        fps = probe_fps(video)
        punches = window(read_sheet(sheet), fps, max_seconds)
        if not punches:
            print(f"{name}: no annotations parsed, skipped")
            continue
        pad = int(pad_seconds * fps)
        first, last = punches[0].start_frame, punches[-1].end_frame
        clip_id = f"boxingvi_{name.lower()}"
        labels = to_labels(clip_id, punches, fps, stances.get(name, "orthodox"), first, pad)
        start_s = max(0.0, (first - pad) / fps)
        cut_excerpt(video, out / f"{clip_id}.mp4", start_s, (last - first) / fps + 2 * pad_seconds)
        (out / f"{clip_id}.json").write_text(
            json.dumps(labels.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
        written.append(clip_id)
        print(f"{clip_id}: {len(punches)} punches, {fps:g} fps, excerpt from {start_s:.1f} s")
    return written


def _stances(items: Sequence[str]) -> dict[str, Stance]:
    result: dict[str, Stance] = {}
    for item in items:
        name, _, stance = item.partition("=")
        if stance not in ("orthodox", "southpaw"):
            raise SystemExit(f"--stance {item!r}: expected V<n>=orthodox or V<n>=southpaw")
        result[name] = stance  # type: ignore[assignment]
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval.public_sets.boxingvi", description=__doc__
    )
    sub = parser.add_subparsers(dest="command", required=True)
    conv = sub.add_parser("convert")
    conv.add_argument("--annotations", type=Path, required=True)
    conv.add_argument("--videos", type=Path, required=True)
    conv.add_argument("--out", type=Path, required=True)
    conv.add_argument("--max-seconds", type=float, default=180.0, help="0 for everything")
    conv.add_argument("--stance", action="append", default=[], metavar="V1=southpaw")
    args = parser.parse_args(argv)
    convert(
        args.annotations, args.videos, args.out, _stances(args.stance), args.max_seconds or None
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
