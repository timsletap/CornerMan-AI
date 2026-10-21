"""Quality gates for collected clips.

The pipeline assumes one continuous, landscape camera shot at normal speed. Clips that
are edited (many scene cuts), portrait, too small, too short, or low frame rate are
rejected. Slow-motion replays usually come with cuts, so the cut rate also catches most
highlight edits. An optional pose check (``--pose-check``) samples frames and requires
a clearly visible person.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

SCENE_THRESHOLD = 0.35
"""ffmpeg scene-change score above which a frame counts as a cut (0..1)."""


@dataclass(frozen=True)
class QualityRules:
    min_height: int = 480
    min_fps: float = 24.0
    min_duration_s: float = 5.0
    max_duration_s: float = 1800.0
    max_cuts_per_min: float = 2.0
    min_person_fraction: float = 0.7


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    fps: float
    duration_s: float


def probe(path: Path) -> ProbeResult:
    """Read video stream size, frame rate, and duration with ffprobe."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_read_packets:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    data = json.loads(out)
    streams = data.get("streams") or []
    if not streams:
        raise ValueError("no video stream")
    stream = streams[0]
    duration = float(data.get("format", {}).get("duration", 0.0))
    return ProbeResult(
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=measured_fps(stream, duration),
        duration_s=duration,
    )


def measured_fps(stream: dict[str, str], duration_s: float) -> float:
    """Frames per second from packet count / duration.

    The header rates are unreliable for WebM/Matroska (often the 1/1000 time base, e.g.
    ``1000/1``), so the counted packets are preferred when available.
    """
    packets = int(stream.get("nb_read_packets") or 0)
    if packets > 0 and duration_s > 0:
        return packets / duration_s
    rate = stream.get("avg_frame_rate") or "0/1"
    return float(Fraction(rate)) if not rate.endswith("/0") else 0.0


_PTS_TIME = re.compile(r"pts_time:\s*([\d.]+)")


def parse_cut_times(ffmpeg_stderr: str) -> list[float]:
    """Cut timestamps (s) from ffmpeg ``select=gt(scene,x),showinfo`` output."""
    return [float(m) for m in _PTS_TIME.findall(ffmpeg_stderr)]


def detect_cuts(path: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Times (s) of hard scene cuts, found with ffmpeg's scene-change score."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-an",
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if proc.returncode != 0:
        raise ValueError(f"ffmpeg could not decode the clip: {proc.stderr[-300:]}")
    return parse_cut_times(proc.stderr)


def check_rules(
    info: ProbeResult,
    cut_times: list[float],
    rules: QualityRules,
    person_fraction: float | None = None,
) -> list[str]:
    """Reasons to reject a clip; empty when it passes."""
    reasons: list[str] = []
    if info.width < info.height:
        reasons.append(f"portrait {info.width}x{info.height} (need landscape)")
    if info.height < rules.min_height:
        reasons.append(f"height {info.height}px < {rules.min_height}px")
    if info.fps < rules.min_fps:
        reasons.append(f"{info.fps:.1f} fps < {rules.min_fps:g} fps")
    if info.duration_s < rules.min_duration_s:
        reasons.append(f"duration {info.duration_s:.1f}s < {rules.min_duration_s:g}s")
    if info.duration_s > rules.max_duration_s:
        reasons.append(f"duration {info.duration_s:.0f}s > {rules.max_duration_s:g}s")
    if info.duration_s > 0:
        per_min = len(cut_times) / (info.duration_s / 60)
        if per_min > rules.max_cuts_per_min:
            reasons.append(
                f"{len(cut_times)} scene cuts ({per_min:.1f}/min > {rules.max_cuts_per_min:g}/min);"
                " edited footage"
            )
    if person_fraction is not None and person_fraction < rules.min_person_fraction:
        reasons.append(
            f"person clearly visible in {person_fraction:.0%} of sampled frames "
            f"(< {rules.min_person_fraction:.0%})"
        )
    return reasons


def person_fraction(path: Path, model_name: str, samples: int = 12) -> float:
    """Fraction of evenly spaced frames with a confidently detected person pose.

    A frame counts when some person has mean keypoint confidence >= 0.5.
    """
    import cv2
    from ultralytics import YOLO

    model = YOLO(model_name)
    cap = cv2.VideoCapture(str(path))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return 0.0
        idxs = sorted({int(total * (i + 0.5) / samples) for i in range(samples)})
        hits = 0
        for idx in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            result = model(frame, verbose=False)[0]
            kp = result.keypoints
            if kp is not None and kp.conf is not None and len(kp.conf):
                if float(kp.conf.mean(dim=1).max()) >= 0.5:
                    hits += 1
        return hits / len(idxs)
    finally:
        cap.release()
