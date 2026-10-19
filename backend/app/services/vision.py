"""Vision engine service - YOLOv8-Pose pipeline for strike analysis.

Implements VIS-01 through VIS-07 from the FRD:
- Skeleton tracking (17 COCO keypoints)
- Strike detection via wrist velocity spikes
- Guard analysis (off-hand wrist-to-nose distance)
- Telegraph detection (elbow flare in pre-strike frames)
- Subject isolation (primary actor scoring)
- Occlusion handling (pause/resume on confidence drops)
- Annotated video generation with skeleton overlay
"""

import math
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

from app.config import settings
from app.services.progress import update_progress

COCO_KEYPOINTS = {
    0: "nose",
    1: "left_eye",
    2: "right_eye",
    3: "left_ear",
    4: "right_ear",
    5: "left_shoulder",
    6: "right_shoulder",
    7: "left_elbow",
    8: "right_elbow",
    9: "left_wrist",
    10: "right_wrist",
    11: "left_hip",
    12: "right_hip",
    13: "left_knee",
    14: "right_knee",
    15: "left_ankle",
    16: "right_ankle",
}

# Keypoint indices
NOSE = 0
LEFT_EYE, RIGHT_EYE = 1, 2
LEFT_EAR, RIGHT_EAR = 3, 4
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_ELBOW, RIGHT_ELBOW = 7, 8
LEFT_WRIST, RIGHT_WRIST = 9, 10
LEFT_HIP, RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16

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


@dataclass
class FrameKeypoints:
    frame_number: int
    timestamp_ms: int
    keypoints: list[tuple[float, float, float]]  # 17 entries of (x, y, conf)
    bbox: tuple[float, float, float, float]
    bbox_area: float


@dataclass
class StrikeDetection:
    frame_number: int
    timestamp_ms: int
    hand: str
    velocity: float
    velocity_vector: tuple[float, float]
    wrist_position: tuple[float, float]
    strike_type: str = ""
    keypoints_snapshot: dict = field(default_factory=dict)


@dataclass
class ErrorDetection:
    frame_number: int
    timestamp_ms: int
    error_type: str
    severity: str
    details: dict
    related_strike_index: int | None = None


class VisionPipeline:
    def __init__(self, video_path: str, session_id: uuid.UUID):
        self.video_path = video_path
        self.session_id = session_id
        self.session_id_str = str(session_id)
        self.model = YOLO(settings.YOLO_MODEL_NAME)

        self.cap: cv2.VideoCapture | None = None
        self.fps = 30.0
        self.total_frames = 0
        self.frame_width = 0
        self.frame_height = 0

        self.frame_keypoints: list[FrameKeypoints] = []
        self.active_frames: set[int] = set()
        self.occluded_ranges: list[tuple[int, int]] = []

        self.strikes: list[StrikeDetection] = []
        self.errors: list[ErrorDetection] = []

        # For annotated video: store raw keypoints per frame
        self._frame_data: dict[int, dict] = {}
        self.annotated_video_path: str | None = None

    def load_video(self) -> None:
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open video: {self.video_path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def extract_poses(self) -> None:
        """VIS-01 + VIS-06: Run YOLOv8-Pose, select primary actor per frame."""
        frame_center = (self.frame_width / 2, self.frame_height / 2)
        frame_num = 0

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            if frame_num % max(1, settings.VISION_FRAME_SKIP) != 0:
                frame_num += 1
                continue

            # Report progress
            if frame_num % 10 == 0:
                pct = frame_num / max(1, self.total_frames)
                update_progress(
                    self.session_id_str,
                    "pose_extraction",
                    pct * 0.6,  # Pose extraction is 0-60% of total
                    f"Tracking poses: frame {frame_num}/{self.total_frames}",
                )

            timestamp_ms = int((frame_num / self.fps) * 1000)
            results = self.model(frame, verbose=False)

            if results[0].keypoints is None or len(results[0].keypoints.data) == 0:
                frame_num += 1
                continue

            keypoints_data = results[0].keypoints.data.cpu().numpy()
            boxes = results[0].boxes.xyxy.cpu().numpy()

            best_person = self._select_primary_actor(keypoints_data, boxes, frame_center)

            if best_person is not None:
                kps = keypoints_data[best_person]
                box = boxes[best_person]
                bbox_area = float((box[2] - box[0]) * (box[3] - box[1]))

                kp_list = [
                    (float(kps[i][0]), float(kps[i][1]), float(kps[i][2])) for i in range(17)
                ]

                fk = FrameKeypoints(
                    frame_number=frame_num,
                    timestamp_ms=timestamp_ms,
                    keypoints=kp_list,
                    bbox=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    bbox_area=bbox_area,
                )
                self.frame_keypoints.append(fk)
                self.active_frames.add(frame_num)

                # Store for annotated video
                self._frame_data[frame_num] = {
                    "keypoints": kp_list,
                    "bbox": fk.bbox,
                    "all_keypoints": keypoints_data.tolist(),
                    "all_boxes": boxes.tolist(),
                }

            frame_num += 1

        self.cap.release()

    def _select_primary_actor(
        self,
        keypoints_data: np.ndarray,
        boxes: np.ndarray,
        frame_center: tuple[float, float],
    ) -> int | None:
        """VIS-06: Score each person by bbox area (60%) + center proximity (40%)."""
        if len(boxes) == 0:
            return None

        max_diagonal = (self.frame_width**2 + self.frame_height**2) ** 0.5
        frame_area = self.frame_width * self.frame_height

        best_idx = None
        best_score = -1.0

        for i, box in enumerate(boxes):
            avg_conf = float(keypoints_data[i][:, 2].mean())
            if avg_conf < settings.OCCLUSION_CONFIDENCE_THRESHOLD:
                continue

            bbox_area = (box[2] - box[0]) * (box[3] - box[1])
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            center_dist = ((cx - frame_center[0]) ** 2 + (cy - frame_center[1]) ** 2) ** 0.5

            area_score = bbox_area / frame_area
            center_score = 1.0 - (center_dist / max_diagonal)

            score = area_score * 0.6 + center_score * 0.4
            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx

    def handle_occlusion(self) -> None:
        """VIS-07: Mark frame ranges where primary actor was occluded > 0.5s."""
        if not self.frame_keypoints:
            return

        analyzed_set = {fk.frame_number for fk in self.frame_keypoints}
        skip = max(1, settings.VISION_FRAME_SKIP)
        expected_frames = sorted(range(0, self.total_frames, skip))
        missing_frames = sorted(set(expected_frames) - analyzed_set)

        if not missing_frames:
            return

        threshold_frames = max(1, int(settings.OCCLUSION_PAUSE_SECONDS * self.fps / skip))
        current_start = missing_frames[0]
        current_end = missing_frames[0]

        for f in missing_frames[1:]:
            if f <= current_end + skip:
                current_end = f
            else:
                gap_len = (current_end - current_start) // skip + 1
                if gap_len >= threshold_frames:
                    self.occluded_ranges.append((current_start, current_end))
                    for af in range(current_start, current_end + 1):
                        self.active_frames.discard(af)
                current_start = f
                current_end = f

        gap_len = (current_end - current_start) // skip + 1
        if gap_len >= threshold_frames:
            self.occluded_ranges.append((current_start, current_end))

    def detect_strikes(self) -> None:
        """VIS-02: Detect strike events from wrist velocity spikes."""
        if len(self.frame_keypoints) < 3:
            return

        update_progress(
            self.session_id_str,
            "strike_detection",
            0.65,
            "Detecting strikes from velocity data...",
        )

        for hand_idx, hand_name in [(LEFT_WRIST, "left"), (RIGHT_WRIST, "right")]:
            velocities: list[tuple[float, float, float]] = []  # (mag, dx, dy)

            for i in range(1, len(self.frame_keypoints)):
                prev = self.frame_keypoints[i - 1]
                curr = self.frame_keypoints[i]

                if curr.frame_number not in self.active_frames:
                    velocities.append((0.0, 0.0, 0.0))
                    continue

                if prev.keypoints[hand_idx][2] < 0.5 or curr.keypoints[hand_idx][2] < 0.5:
                    velocities.append((0.0, 0.0, 0.0))
                    continue

                dx = curr.keypoints[hand_idx][0] - prev.keypoints[hand_idx][0]
                dy = curr.keypoints[hand_idx][1] - prev.keypoints[hand_idx][1]
                frame_gap = (curr.frame_number - prev.frame_number) / self.fps
                if frame_gap <= 0:
                    velocities.append((0.0, 0.0, 0.0))
                    continue

                vel = (dx**2 + dy**2) ** 0.5 / frame_gap
                vel_norm = vel / max(1, self.frame_height)
                velocities.append((vel_norm, dx / frame_gap, dy / frame_gap))

            # Peak detection with debouncing
            threshold = settings.STRIKE_VELOCITY_THRESHOLD
            min_gap_frames = int(self.fps * 0.3)
            last_strike_frame = -min_gap_frames

            for i in range(1, len(velocities) - 1):
                mag = velocities[i][0]
                if mag > threshold and mag >= velocities[i - 1][0] and mag >= velocities[i + 1][0]:
                    fk = self.frame_keypoints[i + 1]
                    if fk.frame_number - last_strike_frame < min_gap_frames:
                        continue

                    snapshot = {
                        COCO_KEYPOINTS[k]: {
                            "x": round(fk.keypoints[k][0], 1),
                            "y": round(fk.keypoints[k][1], 1),
                            "confidence": round(fk.keypoints[k][2], 3),
                        }
                        for k in range(17)
                    }

                    strike = StrikeDetection(
                        frame_number=fk.frame_number,
                        timestamp_ms=fk.timestamp_ms,
                        hand=hand_name,
                        velocity=mag,
                        velocity_vector=(velocities[i][1], velocities[i][2]),
                        wrist_position=(
                            fk.keypoints[hand_idx][0],
                            fk.keypoints[hand_idx][1],
                        ),
                        keypoints_snapshot=snapshot,
                    )
                    self.strikes.append(strike)
                    last_strike_frame = fk.frame_number

        self.strikes.sort(key=lambda s: s.frame_number)

        # Classify strike types
        for strike in self.strikes:
            fk = self._get_frame_keypoints(strike.frame_number)
            if fk:
                strike.strike_type = self._classify_strike(fk, strike.hand, strike.velocity_vector)
            else:
                strike.strike_type = "other"

    def _classify_strike(
        self,
        fk: FrameKeypoints,
        hand: str,
        velocity_vector: tuple[float, float],
    ) -> str:
        """Classify strike type using biomechanical heuristics."""
        wrist_idx = LEFT_WRIST if hand == "left" else RIGHT_WRIST
        elbow_idx = LEFT_ELBOW if hand == "left" else RIGHT_ELBOW
        shoulder_idx = LEFT_SHOULDER if hand == "left" else RIGHT_SHOULDER

        wrist = fk.keypoints[wrist_idx]
        elbow = fk.keypoints[elbow_idx]
        shoulder = fk.keypoints[shoulder_idx]
        nose = fk.keypoints[NOSE]
        hip_mid_y = (fk.keypoints[LEFT_HIP][1] + fk.keypoints[RIGHT_HIP][1]) / 2

        dx, dy = velocity_vector

        # Body shot: wrist below shoulder midline
        shoulder_hip_mid = shoulder[1] + (hip_mid_y - shoulder[1]) * 0.3
        if wrist[1] > shoulder_hip_mid:
            return "body_shot"

        # Uppercut: dominant upward movement (negative dy in image coords)
        if abs(dy) > abs(dx) * 1.5 and dy < 0:
            return "uppercut"

        # Hook: large horizontal component + bent elbow
        elbow_angle = self._compute_angle(shoulder, elbow, wrist)
        if abs(dx) > abs(dy) * 1.2 and elbow_angle < 120:
            return "hook"

        # Cross vs Jab: based on arm extension relative to torso
        arm_ext = ((wrist[0] - shoulder[0]) ** 2 + (wrist[1] - shoulder[1]) ** 2) ** 0.5
        torso_height = abs(nose[1] - hip_mid_y) if nose[2] > 0.5 else self.frame_height * 0.4
        if torso_height > 0 and arm_ext / torso_height > 0.8:
            return "cross"

        return "jab"

    @staticmethod
    def _compute_angle(a, b, c) -> float:
        """Compute angle at point b (each point is (x, y, conf))."""
        ba = (a[0] - b[0], a[1] - b[1])
        bc = (c[0] - b[0], c[1] - b[1])
        dot = ba[0] * bc[0] + ba[1] * bc[1]
        mag_ba = (ba[0] ** 2 + ba[1] ** 2) ** 0.5
        mag_bc = (bc[0] ** 2 + bc[1] ** 2) ** 0.5
        if mag_ba * mag_bc == 0:
            return 180.0
        cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
        return math.degrees(math.acos(cos_angle))

    def analyze_guard(self) -> None:
        """VIS-03: Check off-hand guard integrity during each strike."""
        update_progress(
            self.session_id_str,
            "guard_analysis",
            0.70,
            "Analyzing guard integrity...",
        )

        for strike_idx, strike in enumerate(self.strikes):
            fk = self._get_frame_keypoints(strike.frame_number)
            if fk is None:
                continue

            off_wrist_idx = RIGHT_WRIST if strike.hand == "left" else LEFT_WRIST
            off_wrist = fk.keypoints[off_wrist_idx]
            nose = fk.keypoints[NOSE]

            if off_wrist[2] < 0.5 or nose[2] < 0.5:
                continue

            distance = ((off_wrist[0] - nose[0]) ** 2 + (off_wrist[1] - nose[1]) ** 2) ** 0.5
            hip_mid_y = (fk.keypoints[LEFT_HIP][1] + fk.keypoints[RIGHT_HIP][1]) / 2
            torso_height = abs(nose[1] - hip_mid_y)
            if torso_height < 10:
                continue

            normalized_dist = distance / torso_height
            if normalized_dist > settings.GUARD_DISTANCE_THRESHOLD:
                if normalized_dist > settings.GUARD_DISTANCE_THRESHOLD * 2.0:
                    severity = "high"
                elif normalized_dist > settings.GUARD_DISTANCE_THRESHOLD * 1.5:
                    severity = "medium"
                else:
                    severity = "low"

                self.errors.append(
                    ErrorDetection(
                        frame_number=strike.frame_number,
                        timestamp_ms=strike.timestamp_ms,
                        error_type="dropped_guard",
                        severity=severity,
                        details={
                            "off_hand": "right" if strike.hand == "left" else "left",
                            "normalized_distance": round(normalized_dist, 3),
                            "threshold": settings.GUARD_DISTANCE_THRESHOLD,
                        },
                        related_strike_index=strike_idx,
                    )
                )

    def detect_telegraph(self) -> None:
        """VIS-04: Detect elbow flare (chicken wing) in 10 pre-strike frames."""
        update_progress(
            self.session_id_str,
            "telegraph_detection",
            0.75,
            "Detecting telegraph patterns...",
        )

        for strike_idx, strike in enumerate(self.strikes):
            elbow_idx = LEFT_ELBOW if strike.hand == "left" else RIGHT_ELBOW

            pre_frames = [
                fk for fk in self.frame_keypoints if fk.frame_number < strike.frame_number
            ][-10:]

            if len(pre_frames) < 5:
                continue

            elbow_x_coords = [
                fk.keypoints[elbow_idx][0] for fk in pre_frames if fk.keypoints[elbow_idx][2] >= 0.5
            ]

            if len(elbow_x_coords) < 3:
                continue

            mean_x = sum(elbow_x_coords) / len(elbow_x_coords)
            if mean_x == 0:
                continue
            variance = sum((x - mean_x) ** 2 for x in elbow_x_coords) / len(elbow_x_coords)
            std_x = variance**0.5
            cov = std_x / abs(mean_x)

            if cov > settings.TELEGRAPH_VARIANCE_THRESHOLD:
                if cov > settings.TELEGRAPH_VARIANCE_THRESHOLD * 2.5:
                    severity = "high"
                elif cov > settings.TELEGRAPH_VARIANCE_THRESHOLD * 1.5:
                    severity = "medium"
                else:
                    severity = "low"

                self.errors.append(
                    ErrorDetection(
                        frame_number=strike.frame_number,
                        timestamp_ms=strike.timestamp_ms,
                        error_type="chicken_wing",
                        severity=severity,
                        details={
                            "hand": strike.hand,
                            "elbow_x_variance": round(cov, 4),
                            "threshold": settings.TELEGRAPH_VARIANCE_THRESHOLD,
                            "pre_strike_frames_analyzed": len(elbow_x_coords),
                        },
                        related_strike_index=strike_idx,
                    )
                )

    def generate_annotated_video(self) -> str | None:
        """Generate video with skeleton overlay, strike markers, and HUD stats."""
        update_progress(
            self.session_id_str,
            "rendering",
            0.78,
            "Rendering annotated video with tracking overlay...",
        )

        video_dir = Path(self.video_path).parent
        annotated_path = str(video_dir / f"{self.session_id}_annotated.mp4")

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            return None

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(
            annotated_path,
            fourcc,
            self.fps,
            (self.frame_width, self.frame_height),
        )

        # Pre-compute strike and error lookup by frame
        strike_frames = {s.frame_number: s for s in self.strikes}
        error_frames: dict[int, list[ErrorDetection]] = {}
        for e in self.errors:
            error_frames.setdefault(e.frame_number, []).append(e)

        # Track running stats for HUD
        strikes_so_far = 0
        errors_so_far = 0
        last_strike_type = ""
        recent_velocity = 0.0

        frame_num = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Progress for rendering
            if frame_num % 30 == 0:
                render_pct = 0.78 + (frame_num / max(1, self.total_frames)) * 0.12
                update_progress(
                    self.session_id_str,
                    "rendering",
                    render_pct,
                    f"Rendering frame {frame_num}/{self.total_frames}",
                )

            # Check if we have pose data for this frame
            fd = self._frame_data.get(frame_num)
            is_strike_frame = frame_num in strike_frames
            frame_errors = error_frames.get(frame_num, [])

            if is_strike_frame:
                strikes_so_far += 1
                s = strike_frames[frame_num]
                last_strike_type = s.strike_type
                recent_velocity = s.velocity
            if frame_errors:
                errors_so_far += len(frame_errors)

            if fd:
                kps = fd["keypoints"]

                # Draw skeleton connections
                self._draw_skeleton(frame, kps, is_strike_frame)

                # Draw keypoint dots
                self._draw_keypoints(frame, kps, is_strike_frame)

                # Draw bounding box (subtle)
                bbox = fd["bbox"]
                x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                box_color = STRIKE_FLASH_COLOR if is_strike_frame else BBOX_COLOR
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 1)

                # If strike frame: draw velocity vector and flash
                if is_strike_frame:
                    self._draw_strike_overlay(frame, strike_frames[frame_num], kps)

                # If error frame: draw guard distance line
                for err in frame_errors:
                    self._draw_error_overlay(frame, err, kps)

            # Draw HUD overlay (always)
            timestamp_s = frame_num / self.fps
            self._draw_hud(
                frame,
                frame_num,
                timestamp_s,
                strikes_so_far,
                errors_so_far,
                last_strike_type,
                recent_velocity,
                fd is not None,
                is_strike_frame,
            )

            out.write(frame)
            frame_num += 1

        cap.release()
        out.release()

        # Transcode from mpeg4 to h264 so browsers can play it
        h264_path = str(video_dir / f"{self.session_id}_annotated_h264.mp4")
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    annotated_path,
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
            Path(annotated_path).unlink(missing_ok=True)
            Path(h264_path).rename(annotated_path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Fall back to the mpeg4 version if transcode fails
            pass

        self.annotated_video_path = annotated_path
        return annotated_path

    def _draw_skeleton(self, frame: np.ndarray, kps: list, is_strike: bool) -> None:
        """Draw skeleton lines between connected keypoints."""
        for i, j in SKELETON_CONNECTIONS:
            if kps[i][2] < 0.4 or kps[j][2] < 0.4:
                continue
            pt1 = (int(kps[i][0]), int(kps[i][1]))
            pt2 = (int(kps[j][0]), int(kps[j][1]))
            color = STRIKE_FLASH_COLOR if is_strike else SKELETON_COLOR
            thickness = 3 if is_strike else 2
            cv2.line(frame, pt1, pt2, color, thickness, cv2.LINE_AA)

    def _draw_keypoints(self, frame: np.ndarray, kps: list, is_strike: bool) -> None:
        """Draw keypoint circles with confidence-based sizing."""
        for x, y, conf in kps:
            if conf < 0.4:
                continue
            radius = max(3, int(conf * 6))
            color = STRIKE_FLASH_COLOR if is_strike else KEYPOINT_COLOR
            cv2.circle(frame, (int(x), int(y)), radius, color, -1, cv2.LINE_AA)
            # Inner white dot for visibility
            cv2.circle(
                frame, (int(x), int(y)), max(1, radius - 2), (255, 255, 255), -1, cv2.LINE_AA
            )

    def _draw_strike_overlay(
        self,
        frame: np.ndarray,
        strike: StrikeDetection,
        kps: list,
    ) -> None:
        """Draw strike indicator: velocity vector, type label, flash border."""
        wrist_idx = LEFT_WRIST if strike.hand == "left" else RIGHT_WRIST
        wx, wy = int(kps[wrist_idx][0]), int(kps[wrist_idx][1])

        # Velocity vector arrow
        scale = 0.3
        dx = int(strike.velocity_vector[0] * scale)
        dy = int(strike.velocity_vector[1] * scale)
        cv2.arrowedLine(
            frame,
            (wx, wy),
            (wx + dx, wy + dy),
            VELOCITY_COLOR,
            3,
            cv2.LINE_AA,
            tipLength=0.3,
        )

        # Strike type label
        label = f"{strike.strike_type.upper()} {strike.velocity:.1f}u/s"
        label_y = max(30, wy - 25)
        self._draw_label(frame, label, (wx - 40, label_y), STRIKE_FLASH_COLOR)

        # Screen flash border
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), STRIKE_FLASH_COLOR, 4)

    def _draw_error_overlay(
        self,
        frame: np.ndarray,
        error: ErrorDetection,
        kps: list,
    ) -> None:
        """Draw error indicators: guard distance line, warning markers."""
        if error.error_type == "dropped_guard":
            # Draw line from off-hand wrist to nose showing gap
            off_hand = error.details.get("off_hand", "left")
            wrist_idx = LEFT_WRIST if off_hand == "left" else RIGHT_WRIST
            if kps[wrist_idx][2] >= 0.4 and kps[NOSE][2] >= 0.4:
                pt_wrist = (int(kps[wrist_idx][0]), int(kps[wrist_idx][1]))
                pt_nose = (int(kps[NOSE][0]), int(kps[NOSE][1]))
                cv2.line(frame, pt_wrist, pt_nose, GUARD_LINE_COLOR, 2, cv2.LINE_AA)

                # Distance label
                mid_x = (pt_wrist[0] + pt_nose[0]) // 2
                mid_y = (pt_wrist[1] + pt_nose[1]) // 2
                dist_str = f"GUARD {error.severity.upper()}"
                self._draw_label(frame, dist_str, (mid_x, mid_y), ERROR_COLOR)

        elif error.error_type == "chicken_wing":
            # Highlight elbow
            hand = error.details.get("hand", "right")
            elbow_idx = LEFT_ELBOW if hand == "left" else RIGHT_ELBOW
            if kps[elbow_idx][2] >= 0.4:
                ex, ey = int(kps[elbow_idx][0]), int(kps[elbow_idx][1])
                cv2.circle(frame, (ex, ey), 20, ERROR_COLOR, 3, cv2.LINE_AA)
                self._draw_label(frame, "TELEGRAPH", (ex - 30, ey - 25), ERROR_COLOR)

    def _draw_hud(
        self,
        frame: np.ndarray,
        frame_num: int,
        timestamp_s: float,
        strikes_count: int,
        errors_count: int,
        last_strike: str,
        velocity: float,
        tracking_active: bool,
        is_strike: bool,
    ) -> None:
        """Draw heads-up display with stats overlay."""
        h, w = frame.shape[:2]

        # Top-left: CornerMan branding + timestamp
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (320, 42), HUD_BG, -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        cv2.putText(
            frame,
            "CORNERMAN AI",
            (10, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            HUD_ACCENT,
            1,
            cv2.LINE_AA,
        )
        time_str = f"{int(timestamp_s // 60):02d}:{int(timestamp_s % 60):02d}.{int((timestamp_s % 1) * 10)}"
        cv2.putText(
            frame,
            f"T: {time_str}  F: {frame_num}",
            (10, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            HUD_TEXT,
            1,
            cv2.LINE_AA,
        )

        # Tracking status indicator
        status_color = HUD_GREEN if tracking_active else HUD_RED
        cv2.circle(frame, (300, 20), 6, status_color, -1, cv2.LINE_AA)

        # Top-right: Live stats panel
        panel_w = 260
        overlay2 = frame.copy()
        cv2.rectangle(overlay2, (w - panel_w, 0), (w, 100), HUD_BG, -1)
        cv2.addWeighted(overlay2, 0.7, frame, 0.3, 0, frame)

        x_start = w - panel_w + 10
        cv2.putText(
            frame,
            f"STRIKES: {strikes_count}",
            (x_start, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            HUD_ACCENT,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"ERRORS: {errors_count}",
            (x_start, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            HUD_RED if errors_count > 0 else HUD_TEXT,
            1,
            cv2.LINE_AA,
        )
        if last_strike:
            cv2.putText(
                frame,
                f"LAST: {last_strike.upper()}",
                (x_start, 64),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                HUD_TEXT,
                1,
                cv2.LINE_AA,
            )
        if velocity > 0:
            cv2.putText(
                frame,
                f"VEL: {velocity:.1f} u/s",
                (x_start, 86),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                VELOCITY_COLOR,
                1,
                cv2.LINE_AA,
            )

        # Bottom bar: guard score progress
        guard_score = self.compute_guard_score()
        bar_h = 6
        bar_y = h - bar_h - 4
        bar_w = w - 20
        # Background
        cv2.rectangle(frame, (10, bar_y), (10 + bar_w, bar_y + bar_h), (40, 40, 40), -1)
        # Fill
        fill_w = int(bar_w * guard_score / 100)
        bar_color = (
            HUD_GREEN if guard_score >= 80 else (0, 200, 255) if guard_score >= 50 else HUD_RED
        )
        if fill_w > 0:
            cv2.rectangle(frame, (10, bar_y), (10 + fill_w, bar_y + bar_h), bar_color, -1)
        # Label
        cv2.putText(
            frame,
            f"GUARD: {guard_score:.0f}%",
            (10, bar_y - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            bar_color,
            1,
            cv2.LINE_AA,
        )

    @staticmethod
    def _draw_label(
        frame: np.ndarray,
        text: str,
        pos: tuple[int, int],
        color: tuple[int, int, int],
    ) -> None:
        """Draw a text label with semi-transparent background."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        thickness = 1
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        x, y = pos
        # Background
        overlay = frame.copy()
        cv2.rectangle(overlay, (x - 2, y - th - 4), (x + tw + 4, y + 4), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)

    def _get_frame_keypoints(self, frame_number: int) -> FrameKeypoints | None:
        """Find FrameKeypoints closest to the given frame number."""
        best = None
        best_dist = float("inf")
        for fk in self.frame_keypoints:
            dist = abs(fk.frame_number - frame_number)
            if dist < best_dist:
                best_dist = dist
                best = fk
        skip = max(1, settings.VISION_FRAME_SKIP)
        return best if best_dist <= skip * 2 else None

    def compute_guard_score(self) -> float:
        """Guard score: percentage of strikes where guard was maintained."""
        if not self.strikes:
            return 100.0
        guard_errors = sum(1 for e in self.errors if e.error_type == "dropped_guard")
        score = ((len(self.strikes) - guard_errors) / len(self.strikes)) * 100
        return round(max(0.0, score), 1)

    def build_output_json(self) -> dict[str, Any]:
        """VIS-05: Build structured output JSON."""
        avg_velocity = 0.0
        if self.strikes:
            avg_velocity = sum(s.velocity for s in self.strikes) / len(self.strikes)

        duration_sec = self.total_frames / self.fps if self.fps > 0 else 0

        return {
            "session_id": str(self.session_id),
            "video_metadata": {
                "fps": self.fps,
                "total_frames": self.total_frames,
                "duration_seconds": round(duration_sec, 2),
                "resolution": {"width": self.frame_width, "height": self.frame_height},
            },
            "frames_analyzed": len(self.frame_keypoints),
            "primary_actor_detected": len(self.frame_keypoints) > 0,
            "occluded_ranges": [
                {
                    "start_frame": s,
                    "end_frame": e,
                    "start_ms": int(s / self.fps * 1000),
                    "end_ms": int(e / self.fps * 1000),
                }
                for s, e in self.occluded_ranges
            ],
            "strike_events": [
                {
                    "frame_number": s.frame_number,
                    "timestamp_ms": s.timestamp_ms,
                    "hand": s.hand,
                    "strike_type": s.strike_type,
                    "velocity": round(s.velocity, 2),
                    "wrist_position": {
                        "x": round(s.wrist_position[0], 1),
                        "y": round(s.wrist_position[1], 1),
                    },
                    "keypoints": s.keypoints_snapshot,
                }
                for s in self.strikes
            ],
            "error_flags": [
                {
                    "frame_number": e.frame_number,
                    "timestamp_ms": e.timestamp_ms,
                    "error_type": e.error_type,
                    "severity": e.severity,
                    "details": e.details,
                    "related_strike_index": e.related_strike_index,
                }
                for e in self.errors
            ],
            "metrics": {
                "total_strikes": len(self.strikes),
                "avg_velocity": round(avg_velocity, 2),
                "guard_score": self.compute_guard_score(),
                "strikes_per_minute": round(len(self.strikes) / max(1, duration_sec / 60), 1),
                "error_counts": {
                    "dropped_guard": sum(1 for e in self.errors if e.error_type == "dropped_guard"),
                    "chicken_wing": sum(1 for e in self.errors if e.error_type == "chicken_wing"),
                },
            },
            "annotated_video_path": self.annotated_video_path,
        }


def run_vision_analysis(video_path: str, session_id: uuid.UUID) -> dict[str, Any]:
    """Run the full vision pipeline on a video file. Called from Celery (sync)."""
    pipeline = VisionPipeline(video_path, session_id)
    pipeline.load_video()
    pipeline.extract_poses()
    pipeline.handle_occlusion()
    pipeline.detect_strikes()
    pipeline.analyze_guard()
    pipeline.detect_telegraph()
    pipeline.generate_annotated_video()
    return pipeline.build_output_json()
