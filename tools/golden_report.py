"""Measure the vision pipeline on the golden clip and keep the README's numbers honest.

Usage (from the repo root, with ``backend`` on PYTHONPATH; ``make golden-report`` does this):
    python -m tools.golden_report run       # run the pipeline, write docs/reports/golden_run.json
    python -m tools.golden_report readme    # rewrite the README block from that report
    python -m tools.golden_report check     # exit 1 if the README block is out of date

``run`` times stage 1 (pose model) and stages 2 to 3 (strike and error analysis on cached
poses) separately, and records whether the detections equal ``tests/golden/expected_v1.json``.
These are throughput and regression numbers for one clip. They say nothing about accuracy:
that needs labeled clips (see eval/LABELING.md).

Times are wall-clock seconds on the machine named in the report's ``hardware`` field.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "reports" / "golden_run.json"
README = ROOT / "README.md"
START, END = "<!-- golden:start -->", "<!-- golden:end -->"
STAGE23_REPEATS = 25


def _git_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    return out.stdout.strip() or "unknown"


def _hardware() -> str:
    import torch

    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only"
    cpu = platform.processor() or platform.machine()
    return f"{cpu}, {os.cpu_count()} logical cores, {device}, torch {torch.__version__}"


def _load_golden_harness() -> Any:
    """Import tests/golden/golden.py by path (``tests`` is not an importable package)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "golden_harness", ROOT / "tests" / "golden" / "golden.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run() -> dict[str, Any]:
    """Run stages 1 to 3 on the golden clip and return the report."""
    import importlib

    from app.config import settings

    # Loaded dynamically: app.services is outside the mypy --strict packages.
    coaching: Any = importlib.import_module("app.services.coaching")
    drill_mapping: Any = importlib.import_module("app.services.drill_mapping")
    seed: Any = importlib.import_module("app.services.seed_drills")
    from app.vision import pose
    from app.vision.pipeline import analyze_poses, build_output_json
    from app.vision.types import VisionConfig

    golden = _load_golden_harness()
    clip: Path = golden.CLIP
    golden_settings: dict[str, Any] = golden.GOLDEN_SETTINGS

    with mock.patch.multiple(settings, **golden_settings):
        cfg = VisionConfig.from_settings()
        pose.extract_poses(str(clip), cfg)  # warm-up: model load and first-inference setup

        t0 = time.perf_counter()
        poses = pose.extract_poses(str(clip), cfg)
        stage1_s = time.perf_counter() - t0

        timings = []
        for _ in range(STAGE23_REPEATS):
            t0 = time.perf_counter()
            analysis = analyze_poses(poses, cfg)
            timings.append(time.perf_counter() - t0)

        output = build_output_json(golden.SESSION_ID, analysis, None, None)

    meta = poses.meta
    clip_s = meta.total_frames / meta.fps
    stage23_s = statistics.median(timings)
    expected = json.loads(golden.EXPECTED.read_text(encoding="utf-8"))
    actual: dict[str, Any] = golden.normalize(output)
    drills_by_name: dict[str, Any] = {d["name"]: d for d in seed.SEED_DRILLS}
    error_types = sorted({e["error_type"] for e in output["error_flags"]})

    return {
        "git_sha": _git_sha(),
        "clip": {
            "path": clip.relative_to(ROOT).as_posix(),
            "duration_s": round(clip_s, 2),
            "fps": round(meta.fps, 2),
            "frames": meta.total_frames,
            "resolution": f"{meta.width}x{meta.height}",
        },
        "model": cfg.model_name,
        "settings": golden_settings,
        "hardware": _hardware(),
        "throughput": {
            "stage1_seconds": round(stage1_s, 2),
            "stage1_fps": round(meta.total_frames / stage1_s, 1),
            "stage1_x_realtime": round(clip_s / stage1_s, 2),
            "stages23_ms": round(stage23_s * 1000, 1),
            "stages23_x_realtime": round(clip_s / stage23_s),
            "stages23_repeats": STAGE23_REPEATS,
        },
        "detections": {
            "strikes": len(output["strike_events"]),
            "by_type": dict(
                sorted(Counter(s["strike_type"] for s in output["strike_events"]).items())
            ),
            "errors": dict(sorted(Counter(e["error_type"] for e in output["error_flags"]).items())),
            "guard_score": output["metrics"]["guard_score"],
        },
        "matches_golden": {
            key: actual[key] == expected[key] for key in ("strike_events", "error_flags", "metrics")
        },
        # What the app shows for this clip with no LLM key: used for README screenshots.
        "session": {
            "vision": actual,
            "coaching": coaching.fallback_report(output, "Basic report: no LLM key configured."),
            "drills": [
                drills_by_name[name]
                for error_type in error_types
                for name in drill_mapping.get_drills_for_error(error_type)
                if name in drills_by_name
            ],
        },
    }


def readme_block(report: dict[str, Any]) -> str:
    """Markdown generated from the report; every number in it comes from the JSON."""
    clip, tp, det = report["clip"], report["throughput"], report["detections"]
    same = all(report["matches_golden"].values())
    by_type = ", ".join(f"{n} {t.replace('_', ' ')}" for t, n in det["by_type"].items())
    errors = ", ".join(f"{n} {t.replace('_', ' ')}" for t, n in det["errors"].items()) or "none"
    rows = [
        (
            "Clip",
            f"`{clip['path']}`: {clip['duration_s']} s, {clip['frames']} frames, {clip['resolution']} at {clip['fps']} fps",
        ),
        ("Pose model", f"`{report['model']}`"),
        (
            "Stage 1, pose extraction",
            f"{tp['stage1_seconds']} s ({tp['stage1_fps']} frames/s, {tp['stage1_x_realtime']}x real time)",
        ),
        (
            "Stages 2 to 3, from cached poses",
            f"{tp['stages23_ms']} ms median of {tp['stages23_repeats']} runs ({tp['stages23_x_realtime']:,}x real time)",
        ),
        (
            "Detections",
            f"{det['strikes']} strikes ({by_type}); flags: {errors}; guard score {det['guard_score']}%",
        ),
        ("Same as committed golden output", "yes" if same else "**no, see report**"),
        ("Hardware", report["hardware"]),
    ]
    lines = [START, "| | |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    lines += [
        "",
        f"Generated by `python -m tools.golden_report` at `{report['git_sha']}` from "
        "[`docs/reports/golden_run.json`](docs/reports/golden_run.json). The golden run uses "
        "lowered test thresholds so every detector fires; it measures speed and regressions, "
        "not accuracy.",
        END,
    ]
    return "\n".join(lines)


def render_readme(text: str, block: str) -> str:
    start, end = text.find(START), text.find(END)
    if start == -1 or end == -1:
        raise ValueError(f"README.md has no {START} ... {END} block")
    return text[:start] + block + text[end + len(END) :]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.golden_report", description=__doc__)
    parser.add_argument("command", choices=["run", "readme", "check"])
    args = parser.parse_args(argv)

    if args.command == "run":
        report = run()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {REPORT.relative_to(ROOT)}")
        print(
            json.dumps(
                {k: report[k] for k in ("throughput", "detections", "matches_golden")}, indent=2
            )
        )
        return 0

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    current = README.read_text(encoding="utf-8")
    updated = render_readme(current, readme_block(report))
    if args.command == "check":
        if updated != current:
            print(
                "README.md golden block does not match docs/reports/golden_run.json",
                file=sys.stderr,
            )
            return 1
        print("ok")
        return 0
    README.write_text(updated, encoding="utf-8")
    print("updated README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
