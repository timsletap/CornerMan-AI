"""Annotated overlay video: skeleton, strike and error markers, HUD (v1 rendering)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
from cv2.typing import MatLike

from app.vision.types import (
    LEFT_ANKLE,
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_EYE,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_EYE,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    ErrorDetection,
    FrameKeypoints,
    Keypoint,
    StrikeDetection,
    VideoMeta,
)

Frame = MatLike
RenderProgressFn = Callable[[int, int], None]
"""Called as (frame_number, total_frames) every 30th rendered frame."""

# Skeleton connections for drawing
SKELETON_CONNECTIONS = [
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW),
    (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW),
    (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE),
    (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE),
    (RIGHT_KNEE, RIGHT_ANKLE),
    (NOSE, LEFT_EYE),
    (NOSE, RIGHT_EYE),
    (LEFT_EYE, LEFT_EAR),
    (RIGHT_EYE, RIGHT_EAR),
]

# Colors for skeleton (BGR)
SKELETON_COLOR = (0, 255, 170)  # Neon green
SKELETON_COLOR_DIM = (0, 180, 120)  # Dimmer green for limbs
KEYPOINT_COLOR = (0, 200, 255)  # Cyan dots
STRIKE_FLASH_COLOR = (0, 0, 255)  # Red flash for strikes
GUARD_LINE_COLOR = (0, 255, 255)  # Yellow for guard distance
ERROR_COLOR = (0, 50, 255)  # Red-orange for errors
VELOCITY_COLOR = (255, 100, 0)  # Blue for velocity vectors
BBOX_COLOR = (100, 100, 100)  # Gray bbox

# HUD colors (BGR)
HUD_BG = (20, 20, 20)
HUD_TEXT = (220, 220, 220)
HUD_ACCENT = (0, 200, 255)
HUD_RED = (60, 60, 255)
HUD_GREEN = (60, 220, 60)


def render_annotated(
    video_path: str,
    annotated_path: str,
    meta: VideoMeta,
    frames: Sequence[FrameKeypoints],
    strikes: Sequence[StrikeDetection],
    errors: Sequence[ErrorDetection],
    guard_score: float,
    on_progress: RenderProgressFn | None = None,
) -> str | None:
    """Write the overlay video to ``annotated_path`` (H.264 when ffmpeg is available).

    Returns the path, or None if the source video cannot be opened.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    out = cv2.VideoWriter(annotated_path, fourcc, meta.fps, (meta.width, meta.height))

    by_frame = {fk.frame_number: fk for fk in frames}
    strike_frames = {s.frame_number: s for s in strikes}
    error_frames: dict[int, list[ErrorDetection]] = {}
    for e in errors:
        error_frames.setdefault(e.frame_number, []).append(e)

    # Running stats for the HUD
    strikes_so_far = 0
    errors_so_far = 0
    last_strike_type = ""
    recent_velocity = 0.0

    frame_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if on_progress is not None and frame_num % 30 == 0:
            on_progress(frame_num, meta.total_frames)

        fk = by_frame.get(frame_num)
        is_strike_frame = frame_num in strike_frames
        frame_errors = error_frames.get(frame_num, [])

        if is_strike_frame:
            strikes_so_far += 1
            s = strike_frames[frame_num]
            last_strike_type = s.strike_type
            recent_velocity = s.velocity
        if frame_errors:
            errors_so_far += len(frame_errors)

        if fk:
            kps = fk.keypoints
            _draw_skeleton(frame, kps, is_strike_frame)
            _draw_keypoints(frame, kps, is_strike_frame)

            # Bounding box (subtle)
            x1, y1, x2, y2 = (int(v) for v in fk.bbox)
            box_color = STRIKE_FLASH_COLOR if is_strike_frame else BBOX_COLOR
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 1)

            if is_strike_frame:
                _draw_strike_overlay(frame, strike_frames[frame_num], kps)
            for err in frame_errors:
                _draw_error_overlay(frame, err, kps)

        _draw_hud(
            frame,
            frame_num,
            frame_num / meta.fps,
            strikes_so_far,
            errors_so_far,
            last_strike_type,
            recent_velocity,
            fk is not None,
            guard_score,
        )

        out.write(frame)
        frame_num += 1

    cap.release()
    out.release()
    _transcode_h264(annotated_path)
    return annotated_path


def _transcode_h264(path: str) -> None:
    """Re-encode mpeg4 to H.264 in place so browsers can play it; keep mpeg4 on failure."""
    h264_path = str(Path(path).with_name(Path(path).stem + "_h264.mp4"))
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                path,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-movflags",
                "+faststart",
                "-an",
                h264_path,
            ],
            capture_output=True,
            timeout=600,
            check=True,
        )
        Path(path).unlink(missing_ok=True)
        Path(h264_path).rename(path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass


def _draw_skeleton(frame: Frame, kps: Sequence[Keypoint], is_strike: bool) -> None:
    """Draw skeleton lines between connected keypoints."""
    for i, j in SKELETON_CONNECTIONS:
        if kps[i][2] < 0.4 or kps[j][2] < 0.4:
            continue
        pt1 = (int(kps[i][0]), int(kps[i][1]))
        pt2 = (int(kps[j][0]), int(kps[j][1]))
        color = STRIKE_FLASH_COLOR if is_strike else SKELETON_COLOR
        thickness = 3 if is_strike else 2
        cv2.line(frame, pt1, pt2, color, thickness, cv2.LINE_AA)


def _draw_keypoints(frame: Frame, kps: Sequence[Keypoint], is_strike: bool) -> None:
    """Draw keypoint circles with confidence-based sizing."""
    for x, y, conf in kps:
        if conf < 0.4:
            continue
        radius = max(3, int(conf * 6))
        color = STRIKE_FLASH_COLOR if is_strike else KEYPOINT_COLOR
        cv2.circle(frame, (int(x), int(y)), radius, color, -1, cv2.LINE_AA)
        # Inner white dot for visibility
        cv2.circle(frame, (int(x), int(y)), max(1, radius - 2), (255, 255, 255), -1, cv2.LINE_AA)


def _draw_strike_overlay(frame: Frame, strike: StrikeDetection, kps: Sequence[Keypoint]) -> None:
    """Draw strike indicator: velocity vector, type label, flash border."""
    wrist_idx = LEFT_WRIST if strike.hand == "left" else RIGHT_WRIST
    wx, wy = int(kps[wrist_idx][0]), int(kps[wrist_idx][1])

    scale = 0.3
    dx = int(strike.velocity_vector[0] * scale)
    dy = int(strike.velocity_vector[1] * scale)
    cv2.arrowedLine(
        frame, (wx, wy), (wx + dx, wy + dy), VELOCITY_COLOR, 3, cv2.LINE_AA, tipLength=0.3
    )

    label = f"{strike.strike_type.upper()} {strike.velocity:.1f}u/s"
    label_y = max(30, wy - 25)
    _draw_label(frame, label, (wx - 40, label_y), STRIKE_FLASH_COLOR)

    # Screen flash border
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), STRIKE_FLASH_COLOR, 4)


def _draw_error_overlay(frame: Frame, error: ErrorDetection, kps: Sequence[Keypoint]) -> None:
    """Draw error indicators: guard distance line, warning markers."""
    if error.error_type == "dropped_guard":
        # Line from off-hand wrist to nose showing the gap
        off_hand = error.details.get("off_hand", "left")
        wrist_idx = LEFT_WRIST if off_hand == "left" else RIGHT_WRIST
        if kps[wrist_idx][2] >= 0.4 and kps[NOSE][2] >= 0.4:
            pt_wrist = (int(kps[wrist_idx][0]), int(kps[wrist_idx][1]))
            pt_nose = (int(kps[NOSE][0]), int(kps[NOSE][1]))
            cv2.line(frame, pt_wrist, pt_nose, GUARD_LINE_COLOR, 2, cv2.LINE_AA)

            mid_x = (pt_wrist[0] + pt_nose[0]) // 2
            mid_y = (pt_wrist[1] + pt_nose[1]) // 2
            _draw_label(frame, f"GUARD {error.severity.upper()}", (mid_x, mid_y), ERROR_COLOR)

    elif error.error_type == "chicken_wing":
        hand = error.details.get("hand", "right")
        elbow_idx = LEFT_ELBOW if hand == "left" else RIGHT_ELBOW
        if kps[elbow_idx][2] >= 0.4:
            ex, ey = int(kps[elbow_idx][0]), int(kps[elbow_idx][1])
            cv2.circle(frame, (ex, ey), 20, ERROR_COLOR, 3, cv2.LINE_AA)
            _draw_label(frame, "TELEGRAPH", (ex - 30, ey - 25), ERROR_COLOR)


def _put(
    frame: Frame, text: str, org: tuple[int, int], scale: float, color: tuple[int, int, int]
) -> None:
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def _draw_hud(
    frame: Frame,
    frame_num: int,
    timestamp_s: float,
    strikes_count: int,
    errors_count: int,
    last_strike: str,
    velocity: float,
    tracking_active: bool,
    guard_score: float,
) -> None:
    """Draw heads-up display with stats overlay."""
    h, w = frame.shape[:2]

    # Top-left: CornerMan branding + timestamp
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (320, 42), HUD_BG, -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    _put(frame, "CORNERMAN AI", (10, 18), 0.45, HUD_ACCENT)
    time_str = (
        f"{int(timestamp_s // 60):02d}:{int(timestamp_s % 60):02d}.{int((timestamp_s % 1) * 10)}"
    )
    _put(frame, f"T: {time_str}  F: {frame_num}", (10, 36), 0.4, HUD_TEXT)

    # Tracking status indicator
    status_color = HUD_GREEN if tracking_active else HUD_RED
    cv2.circle(frame, (300, 20), 6, status_color, -1, cv2.LINE_AA)

    # Top-right: live stats panel
    panel_w = 260
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (w - panel_w, 0), (w, 100), HUD_BG, -1)
    cv2.addWeighted(overlay2, 0.7, frame, 0.3, 0, frame)

    x_start = w - panel_w + 10
    _put(frame, f"STRIKES: {strikes_count}", (x_start, 20), 0.5, HUD_ACCENT)
    errors_color = HUD_RED if errors_count > 0 else HUD_TEXT
    _put(frame, f"ERRORS: {errors_count}", (x_start, 42), 0.5, errors_color)
    if last_strike:
        _put(frame, f"LAST: {last_strike.upper()}", (x_start, 64), 0.45, HUD_TEXT)
    if velocity > 0:
        _put(frame, f"VEL: {velocity:.1f} u/s", (x_start, 86), 0.45, VELOCITY_COLOR)

    # Bottom bar: guard score
    bar_h = 6
    bar_y = h - bar_h - 4
    bar_w = w - 20
    cv2.rectangle(frame, (10, bar_y), (10 + bar_w, bar_y + bar_h), (40, 40, 40), -1)
    fill_w = int(bar_w * guard_score / 100)
    bar_color = HUD_GREEN if guard_score >= 80 else (0, 200, 255) if guard_score >= 50 else HUD_RED
    if fill_w > 0:
        cv2.rectangle(frame, (10, bar_y), (10 + fill_w, bar_y + bar_h), bar_color, -1)
    _put(frame, f"GUARD: {guard_score:.0f}%", (10, bar_y - 6), 0.35, bar_color)


def _draw_label(frame: Frame, text: str, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
    """Draw a text label with semi-transparent background."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.45
    thickness = 1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x, y = pos
    overlay = frame.copy()
    cv2.rectangle(overlay, (x - 2, y - th - 4), (x + tw + 4, y + 4), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)
