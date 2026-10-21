"""Label and split schemas for the eval set (FRD section 6.5) and a validator CLI.

Usage:
    python -m eval.schema validate eval/labels/ [--clips-dir eval/clips]
    python -m eval.schema validate-splits eval/splits.yaml [--labels-dir eval/labels]

Times are integer milliseconds from video start (``t_ms``); ``t_ms`` is the frame of
full extension. Hands are the fighter's anatomical hands.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Stance = Literal["orthodox", "southpaw"]
Hand = Literal["left", "right"]
StrikeType = Literal["jab", "cross", "hook", "uppercut", "body_shot"]
Target = Literal["head", "body"]
ErrorType = Literal["dropped_guard", "chicken_wing"]
Tag = Literal[
    "bag",
    "pads",
    "shadow",
    "sparring",
    "near",
    "far",
    "side",
    "three_quarter",
    "head_on",
    "indoor",
    "outdoor",
]

STRIKE_TYPES: tuple[str, ...] = get_args(StrikeType)
ERROR_TYPES: tuple[str, ...] = get_args(ErrorType)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Fighter(_Strict):
    stance: Stance
    track_hint: str | None = None


class StrikeLabel(_Strict):
    t_ms: int = Field(ge=0, description="Frame of full extension, ms from video start")
    hand: Hand
    type: StrikeType
    target: Target


class ErrorLabel(_Strict):
    t_ms: int = Field(ge=0, description="Time of the strike the error belongs to, ms")
    type: ErrorType
    hand: Hand


class SkippedSpan(_Strict):
    """A span the labeler deliberately left unlabeled (ambiguous strikes, occlusion)."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    reason: str

    @model_validator(mode="after")
    def _ordered(self) -> SkippedSpan:
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) is before start_ms ({self.start_ms})")
        return self


class ClipLabels(_Strict):
    clip_id: str = Field(min_length=1)
    fps: float = Field(gt=0, description="Source frames per second")
    tags: list[Tag] = []
    fighter: Fighter
    strikes: list[StrikeLabel] = []
    errors: list[ErrorLabel] = []
    notes: list[SkippedSpan] = []
    labeler: str = Field(min_length=1)
    label_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _consistent(self) -> ClipLabels:
        times = [s.t_ms for s in self.strikes]
        for i in range(1, len(times)):
            if times[i] < times[i - 1]:
                raise ValueError(
                    f"strikes must be sorted by t_ms: strikes[{i}].t_ms={times[i]} "
                    f"comes after strikes[{i - 1}].t_ms={times[i - 1]}"
                )
        seen: dict[tuple[str, int], int] = {}
        for i, s in enumerate(self.strikes):
            key = (s.hand, s.t_ms)
            if key in seen:
                raise ValueError(
                    f"duplicate strike (hand={s.hand}, t_ms={s.t_ms}) at strikes[{seen[key]}] "
                    f"and strikes[{i}]"
                )
            seen[key] = i
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tags contain duplicates")
        return self

    def max_t_ms(self) -> int:
        """Latest time referenced anywhere in the labels, in ms."""
        times = [s.t_ms for s in self.strikes] + [e.t_ms for e in self.errors]
        times += [n.end_ms for n in self.notes]
        return max(times, default=0)


class Splits(_Strict):
    dev: list[str] = []
    test: list[str] = []
    seed: list[str] = Field(default=[], description="DATA-01 starting set; subset of dev")
    fighters: dict[str, str] = Field(default={}, description="clip_id -> anonymous fighter id")

    @model_validator(mode="after")
    def _disjoint(self) -> Splits:
        for name in ("dev", "test", "seed"):
            clips: list[str] = getattr(self, name)
            dupes = sorted({c for c in clips if clips.count(c) > 1})
            if dupes:
                raise ValueError(f"{name} lists clips more than once: {dupes}")
        both = sorted(set(self.dev) & set(self.test))
        if both:
            raise ValueError(f"clips in both dev and test: {both}")
        not_dev = sorted(set(self.seed) - set(self.dev))
        if not_dev:
            raise ValueError(f"seed clips must also be in dev: {not_dev}")
        unmapped = sorted(c for c in self.dev + self.test if c not in self.fighters)
        if unmapped:
            raise ValueError(f"clips missing from fighters: {unmapped}")
        dev_fighters = {self.fighters[c] for c in self.dev}
        test_fighters = {self.fighters[c] for c in self.test}
        shared = sorted(dev_fighters & test_fighters)
        if shared:
            raise ValueError(f"fighters in both dev and test (split must be by fighter): {shared}")
        return self


def _format_loc(loc: Sequence[int | str]) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _format_errors(source: str, exc: ValidationError) -> list[str]:
    messages = []
    for err in exc.errors():
        loc = _format_loc(err["loc"])
        where = f"{source}: {loc}" if loc else source
        if err["type"] == "literal_error":
            expected = err.get("ctx", {}).get("expected", "")
            messages.append(f"{where}: invalid value {err['input']!r} (expected {expected})")
        else:
            messages.append(f"{where}: {err['msg']}")
    return messages


def clip_duration_ms(path: Path) -> int | None:
    """Duration of a video file in ms, or None if it can't be read."""
    import cv2  # local import: only needed when clips are present

    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    finally:
        cap.release()
    if fps <= 0 or frames <= 0:
        return None
    return int(frames / fps * 1000)


def load_labels(path: Path) -> ClipLabels:
    """Parse and validate one label file. Raises ValidationError or ValueError."""
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    return ClipLabels.model_validate(data)


def validate_label_file(path: Path, clips_dir: Path | None = None) -> list[str]:
    """Return human-readable problems with one label file (empty if valid)."""
    try:
        labels = load_labels(path)
    except json.JSONDecodeError as exc:
        return [f"{path}: invalid JSON: {exc}"]
    except ValidationError as exc:
        return _format_errors(str(path), exc)

    problems = []
    if path.stem != labels.clip_id:
        problems.append(f"{path}: clip_id {labels.clip_id!r} does not match file name")
    if clips_dir is not None:
        clip = next(iter(sorted(clips_dir.glob(f"{labels.clip_id}.*"))), None)
        duration = clip_duration_ms(clip) if clip else None
        if duration is not None and labels.max_t_ms() > duration:
            problems.append(
                f"{path}: t_ms {labels.max_t_ms()} is past the end of {clip} ({duration} ms)"
            )
    return problems


def validate_labels_dir(labels_dir: Path, clips_dir: Path | None = None) -> list[str]:
    """Validate every ``*.json`` under ``labels_dir`` (recursively)."""
    files = sorted(labels_dir.rglob("*.json"))
    if not files:
        return [f"{labels_dir}: no label files found"]
    problems: list[str] = []
    for path in files:
        problems += validate_label_file(path, clips_dir)
    return problems


def load_splits(path: Path) -> Splits:
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Splits.model_validate(data)


def validate_splits_file(path: Path, labels_dir: Path | None = None) -> list[str]:
    """Return problems with a splits file; optionally check each clip has a label file."""
    try:
        splits = load_splits(path)
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]
    except ValidationError as exc:
        return _format_errors(str(path), exc)
    if labels_dir is None:
        return []
    labeled = {p.stem for p in labels_dir.rglob("*.json")}
    missing = sorted(c for c in splits.dev + splits.test if c not in labeled)
    return [f"{path}: no label file for clips: {missing}"] if missing else []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.schema", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_labels = sub.add_parser("validate", help="validate label files")
    p_labels.add_argument("labels_dir", type=Path)
    p_labels.add_argument("--clips-dir", type=Path, default=None)
    p_splits = sub.add_parser("validate-splits", help="validate a splits.yaml")
    p_splits.add_argument("splits_file", type=Path)
    p_splits.add_argument("--labels-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.command == "validate":
        problems = validate_labels_dir(args.labels_dir, args.clips_dir)
    else:
        problems = validate_splits_file(args.splits_file, args.labels_dir)

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) found", file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
