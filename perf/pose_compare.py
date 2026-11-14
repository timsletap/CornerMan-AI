"""Compare pose backends on the same clips, without labels.

Labels do not exist yet, so this measures what can be measured honestly: speed, how often
the fighter's wrists are found with confidence, and how much the keypoints shake while
the body is nearly still. It does not measure strike accuracy; that needs the eval set.

Each backend runs in whichever environment has its dependencies, writes one ``.npz`` of
keypoints per clip, and ``report`` puts them side by side:

    python -m perf.pose_compare run --backend rtmw-l --clips <dir-or-files> --out <dir>
    python -m perf.pose_compare run --backend yolov8m-pose --clips ... --out <dir>
    python -m perf.pose_compare report --out <dir> --json docs/reports/pose_compare.json

Units: pixels in the source frame, seconds, frames per second. Jitter is in shoulder
widths so clips of different resolution are comparable.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]
PoseFn = Callable[[Any], tuple[Array, Array]]
"""Frame (BGR image) -> (keypoints [people, K, 2] in pixels, scores [people, K])."""

# COCO-17 indices; whole-body models keep the same first 17.
L_SHOULDER, R_SHOULDER, L_WRIST, R_WRIST = 5, 6, 9, 10
BODY = slice(0, 17)
CONFIDENT = 0.5
STILL_SPEED = 0.5
"""Shoulder-midpoint speed (shoulder widths per second) under which the body counts as still."""

BACKENDS = ("yolov8m-pose", "rtmw-l", "rtmw-x", "rtmpose-m")


def _providers() -> str:
    import onnxruntime as ort

    if hasattr(ort, "preload_dlls"):
        ort.preload_dlls()
    return "cuda" if "CUDAExecutionProvider" in ort.get_available_providers() else "cpu"


def load_backend(name: str) -> tuple[PoseFn, str]:
    """A pose function and the device it runs on."""
    if name == "yolov8m-pose":
        import torch
        from ultralytics import YOLO

        model = YOLO("yolov8m-pose.pt")
        device = "cuda" if torch.cuda.is_available() else "cpu"

        def yolo(frame: Any) -> tuple[Array, Array]:
            result = model(frame, verbose=False, device=device)[0]
            if result.keypoints is None or result.keypoints.conf is None:
                return np.zeros((0, 17, 2)), np.zeros((0, 17))
            return (
                result.keypoints.xy.cpu().numpy().astype(np.float64),
                result.keypoints.conf.cpu().numpy().astype(np.float64),
            )

        return yolo, device

    from rtmlib import Body, Wholebody

    device = _providers()
    if name == "rtmpose-m":
        solution = Body(mode="balanced", backend="onnxruntime", device=device)
    else:
        mode = {"rtmw-l": "balanced", "rtmw-x": "performance"}[name]
        solution = Wholebody(mode=mode, backend="onnxruntime", device=device)

    def rtm(frame: Any) -> tuple[Array, Array]:
        keypoints, scores = solution(frame)
        return np.asarray(keypoints, dtype=np.float64), np.asarray(scores, dtype=np.float64)

    return rtm, device


def frames(path: Path, max_frames: int) -> Iterator[Any]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        for _ in range(max_frames):
            ok, frame = cap.read()
            if not ok:
                return
            yield frame
    finally:
        cap.release()


def video_fps(path: Path) -> float:
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        return float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    finally:
        cap.release()


def largest_person(keypoints: Array, scores: Array) -> tuple[Array, Array]:
    """The person covering the most area: a stand-in for 'the fighter' in a comparison.

    Returns body keypoints [17, 2] and scores [17], NaN and 0 when nobody was found.
    """
    if len(keypoints) == 0:
        return np.full((17, 2), np.nan), np.zeros(17)
    body = keypoints[:, BODY]
    spans = np.nanmax(body, axis=1) - np.nanmin(body, axis=1)
    best = int(np.argmax(spans[:, 0] * spans[:, 1]))
    return body[best], scores[best, BODY]


def run_backend(name: str, clips: Sequence[Path], out: Path, max_frames: int) -> None:
    pose, device = load_backend(name)
    out.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        xy: list[Array] = []
        conf: list[Array] = []
        people: list[int] = []
        seconds: list[float] = []
        for i, frame in enumerate(frames(clip, max_frames)):
            t0 = time.perf_counter()
            keypoints, scores = pose(frame)
            if i >= 5:  # the first calls pay for model warm-up
                seconds.append(time.perf_counter() - t0)
            body, body_scores = largest_person(keypoints, scores)
            xy.append(body)
            conf.append(body_scores)
            people.append(len(keypoints))
        np.savez_compressed(
            out / f"{clip.stem}__{name}.npz",
            xy=np.array(xy),
            conf=np.array(conf),
            people=np.array(people),
            seconds=np.array(seconds),
            fps=video_fps(clip),
            device=device,
        )
        print(f"{name} {clip.name}: {len(xy)} frames on {device}")


def clip_metrics(xy: Array, conf: Array, seconds: Array, fps: float) -> dict[str, float]:
    """Speed, wrist visibility, and still-body jitter for one clip and backend."""
    found = ~np.isnan(xy[:, 0, 0])
    wrists = conf[:, [L_WRIST, R_WRIST]]
    shoulders = xy[:, [L_SHOULDER, R_SHOULDER]]
    width = np.linalg.norm(shoulders[:, 0] - shoulders[:, 1], axis=1)
    scale = float(np.nanmedian(width)) if found.any() else float("nan")
    mid = shoulders.mean(axis=1)
    mid_speed = np.linalg.norm(np.diff(mid, axis=0), axis=1) * fps / scale
    # Jitter: second difference of the wrist position (acceleration noise) on frames where
    # the body is nearly still, so real punches do not count as shake.
    wrist_xy = xy[:, [L_WRIST, R_WRIST]]
    accel = np.linalg.norm(wrist_xy[2:] - 2 * wrist_xy[1:-1] + wrist_xy[:-2], axis=2) / scale
    still = (mid_speed[1:] < STILL_SPEED) & (mid_speed[:-1] < STILL_SPEED)
    still_accel = accel[still]
    return {
        "frames": float(len(xy)),
        "fps": float(1.0 / np.median(seconds)) if len(seconds) else float("nan"),
        "p95_ms": float(np.percentile(seconds, 95) * 1000) if len(seconds) else float("nan"),
        "person_found_share": float(found.mean()),
        "both_wrists_confident_share": float((wrists > CONFIDENT).all(axis=1).mean()),
        "mean_wrist_confidence": float(wrists.mean()),
        "still_frames": float(still.sum()),
        "wrist_jitter_sw": float(np.nanmedian(still_accel)) if still_accel.size else float("nan"),
    }


def build_report(out: Path) -> dict[str, Any]:
    per_clip: dict[str, dict[str, dict[str, float]]] = {}
    devices: dict[str, str] = {}
    for path in sorted(out.glob("*__*.npz")):
        clip, backend = path.stem.rsplit("__", 1)
        data = np.load(path)
        per_clip.setdefault(clip, {})[backend] = clip_metrics(
            data["xy"], data["conf"], data["seconds"], float(data["fps"])
        )
        devices[backend] = str(data["device"])
    backends = sorted(devices)
    summary = {
        backend: {
            key: float(np.nanmean([m[backend][key] for m in per_clip.values() if backend in m]))
            for key in (
                "fps",
                "p95_ms",
                "person_found_share",
                "both_wrists_confident_share",
                "mean_wrist_confidence",
                "wrist_jitter_sw",
            )
        }
        for backend in backends
    }
    return {"devices": devices, "summary": summary, "clips": per_clip}


def format_report(report: dict[str, Any]) -> str:
    rows = [
        "| Backend | Device | fps | p95 ms | Person found | Both wrists confident | Wrist jitter (sw) |",
        "|---|---|---|---|---|---|---|",
    ]
    for backend, m in report["summary"].items():
        rows.append(
            f"| {backend} | {report['devices'][backend]} | {m['fps']:.1f} | {m['p95_ms']:.0f} "
            f"| {m['person_found_share']:.0%} | {m['both_wrists_confident_share']:.0%} "
            f"| {m['wrist_jitter_sw']:.4f} |"
        )
    return "\n".join(rows)


def _clips(paths: Sequence[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found += sorted(p for p in path.iterdir() if p.suffix in {".mp4", ".webm", ".mov"})
        else:
            found.append(path)
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m perf.pose_compare", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--backend", choices=BACKENDS, required=True)
    run.add_argument("--clips", type=Path, nargs="+", required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--max-frames", type=int, default=600)
    rep = sub.add_parser("report")
    rep.add_argument("--out", type=Path, required=True)
    rep.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.command == "run":
        run_backend(args.backend, _clips(args.clips), args.out, args.max_frames)
        return 0
    report = build_report(args.out)
    print(format_report(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
