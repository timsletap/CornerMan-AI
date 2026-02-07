"""Vision engine service - YOLOv8-Pose pipeline for strike analysis.

Implements VIS-01 through VIS-07 from the FRD:
- Skeleton tracking (17 COCO keypoints)
- Strike detection via wrist velocity spikes
- Guard analysis (off-hand wrist-to-nose distance)
- Telegraph detection (elbow flare in pre-strike frames)
- Subject isolation (primary actor scoring)
- Occlusion handling (pause/resume on confidence drops)
"""

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

from app.config import settings

COCO_KEYPOINTS = {
    0: "nose", 1: "left_eye", 2: "right_eye", 3: "left_ear", 4: "right_ear",
    5: "left_shoulder", 6: "right_shoulder", 7: "left_elbow", 8: "right_elbow",
    9: "left_wrist", 10: "right_wrist", 11: "left_hip", 12: "right_hip",
    13: "left_knee", 14: "right_knee", 15: "left_ankle", 16: "right_ankle",
}

# Keypoint indices
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_ELBOW, RIGHT_ELBOW = 7, 8
LEFT_WRIST, RIGHT_WRIST = 9, 10
LEFT_HIP, RIGHT_HIP = 11, 12


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

            timestamp_ms = int((frame_num / self.fps) * 1000)
            results = self.model(frame, verbose=False)

            if (results[0].keypoints is None
                    or len(results[0].keypoints.data) == 0):
                frame_num += 1
                continue

            keypoints_data = results[0].keypoints.data.cpu().numpy()
            boxes = results[0].boxes.xyxy.cpu().numpy()

            best_person = self._select_primary_actor(
                keypoints_data, boxes, frame_center
            )

            if best_person is not None:
                kps = keypoints_data[best_person]
                box = boxes[best_person]
                bbox_area = float((box[2] - box[0]) * (box[3] - box[1]))

                fk = FrameKeypoints(
                    frame_number=frame_num,
                    timestamp_ms=timestamp_ms,
                    keypoints=[
                        (float(kps[i][0]), float(kps[i][1]), float(kps[i][2]))
                        for i in range(17)
                    ],
                    bbox=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    bbox_area=bbox_area,
                )
                self.frame_keypoints.append(fk)
                self.active_frames.add(frame_num)

            frame_num += 1

        self.cap.release()

    def _select_primary_actor(
        self, keypoints_data: np.ndarray, boxes: np.ndarray,
        frame_center: tuple[float, float],
    ) -> int | None:
        """VIS-06: Score each person by bbox area (60%) + center proximity (40%)."""
        if len(boxes) == 0:
            return None

        max_diagonal = (self.frame_width ** 2 + self.frame_height ** 2) ** 0.5
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

        for hand_idx, hand_name in [(LEFT_WRIST, "left"), (RIGHT_WRIST, "right")]:
            velocities: list[tuple[float, float, float]] = []  # (mag, dx, dy)

            for i in range(1, len(self.frame_keypoints)):
                prev = self.frame_keypoints[i - 1]
                curr = self.frame_keypoints[i]

                if curr.frame_number not in self.active_frames:
                    velocities.append((0.0, 0.0, 0.0))
                    continue

                if (prev.keypoints[hand_idx][2] < 0.5
                        or curr.keypoints[hand_idx][2] < 0.5):
                    velocities.append((0.0, 0.0, 0.0))
                    continue

                dx = curr.keypoints[hand_idx][0] - prev.keypoints[hand_idx][0]
                dy = curr.keypoints[hand_idx][1] - prev.keypoints[hand_idx][1]
                frame_gap = (curr.frame_number - prev.frame_number) / self.fps
                if frame_gap <= 0:
                    velocities.append((0.0, 0.0, 0.0))
                    continue

                vel = (dx ** 2 + dy ** 2) ** 0.5 / frame_gap
                vel_norm = vel / max(1, self.frame_height)
                velocities.append((vel_norm, dx / frame_gap, dy / frame_gap))

            # Peak detection with debouncing
            threshold = settings.STRIKE_VELOCITY_THRESHOLD
            min_gap_frames = int(self.fps * 0.3)
            last_strike_frame = -min_gap_frames

            for i in range(1, len(velocities) - 1):
                mag = velocities[i][0]
                if (mag > threshold
                        and mag >= velocities[i - 1][0]
                        and mag >= velocities[i + 1][0]):
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
                strike.strike_type = self._classify_strike(
                    fk, strike.hand, strike.velocity_vector
                )
            else:
                strike.strike_type = "other"

    def _classify_strike(
        self, fk: FrameKeypoints, hand: str, velocity_vector: tuple[float, float],
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

                self.errors.append(ErrorDetection(
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
                ))

    def detect_telegraph(self) -> None:
        """VIS-04: Detect elbow flare (chicken wing) in 10 pre-strike frames."""
        for strike_idx, strike in enumerate(self.strikes):
            elbow_idx = LEFT_ELBOW if strike.hand == "left" else RIGHT_ELBOW

            pre_frames = [
                fk for fk in self.frame_keypoints
                if fk.frame_number < strike.frame_number
            ][-10:]

            if len(pre_frames) < 5:
                continue

            elbow_x_coords = [
                fk.keypoints[elbow_idx][0]
                for fk in pre_frames
                if fk.keypoints[elbow_idx][2] >= 0.5
            ]

            if len(elbow_x_coords) < 3:
                continue

            mean_x = sum(elbow_x_coords) / len(elbow_x_coords)
            if mean_x == 0:
                continue
            variance = sum((x - mean_x) ** 2 for x in elbow_x_coords) / len(elbow_x_coords)
            std_x = variance ** 0.5
            cov = std_x / abs(mean_x)

            if cov > settings.TELEGRAPH_VARIANCE_THRESHOLD:
                if cov > settings.TELEGRAPH_VARIANCE_THRESHOLD * 2.5:
                    severity = "high"
                elif cov > settings.TELEGRAPH_VARIANCE_THRESHOLD * 1.5:
                    severity = "medium"
                else:
                    severity = "low"

                self.errors.append(ErrorDetection(
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
                ))

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
                    "start_frame": s, "end_frame": e,
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
                "strikes_per_minute": round(
                    len(self.strikes) / max(1, duration_sec / 60), 1
                ),
                "error_counts": {
                    "dropped_guard": sum(1 for e in self.errors if e.error_type == "dropped_guard"),
                    "chicken_wing": sum(1 for e in self.errors if e.error_type == "chicken_wing"),
                },
            },
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
    return pipeline.build_output_json()
