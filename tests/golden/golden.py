"""Golden clip harness (QA-02): run the vision pipeline on tests/golden/clip.mp4 and
reduce its output to the parts that must not change during refactors.

Regenerate the expected output deliberately with ``make golden-update`` (only when a
behavior change is intended, and say so in the PR).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

GOLDEN_DIR = Path(__file__).resolve().parent
CLIP = GOLDEN_DIR / "clip.mp4"
EXPECTED = GOLDEN_DIR / "expected_v1.json"

# Fixed so any session id that leaks into output is stable.
SESSION_ID = uuid.UUID("00000000-0000-0000-0000-00000000901d")

# Vision settings pinned for the golden run, so a local .env cannot change the result.
# The v1 default velocity threshold (15 frame heights/s) almost never fires and the
# telegraph threshold rarely does, which would leave the strike, guard, and telegraph
# code untested; these values produce detections of each kind on typical footage.
# The pose model still comes from YOLO_MODEL_NAME (expected output assumes yolov8m-pose).
GOLDEN_SETTINGS: dict[str, Any] = {
    "STRIKE_VELOCITY_THRESHOLD": 1.0,
    "GUARD_DISTANCE_THRESHOLD": 0.35,
    "TELEGRAPH_VARIANCE_THRESHOLD": 0.02,
    "OCCLUSION_CONFIDENCE_THRESHOLD": 0.7,
    "OCCLUSION_PAUSE_SECONDS": 0.5,
    "VISION_FRAME_SKIP": 1,
}


class _NullRedis:
    def setex(self, *args: Any) -> None:
        pass

    def get(self, key: str) -> None:
        return None

    def delete(self, *keys: str) -> None:
        pass


def normalize(output: dict[str, Any]) -> dict[str, Any]:
    """Drop run-specific fields (session id, file paths); keep detections and metrics."""
    return {
        "video_metadata": output["video_metadata"],
        "frames_analyzed": output["frames_analyzed"],
        "occluded_ranges": output["occluded_ranges"],
        "strike_events": [
            {k: s[k] for k in ("frame_number", "timestamp_ms", "hand", "strike_type", "velocity")}
            for s in output["strike_events"]
        ],
        "error_flags": [
            {
                k: e[k]
                for k in (
                    "frame_number",
                    "error_type",
                    "severity",
                    "details",
                    "related_strike_index",
                )
            }
            for e in output["error_flags"]
        ],
        "metrics": output["metrics"],
    }


def run(clip: Path = CLIP) -> dict[str, Any]:
    """Run the full pipeline (including rendering) on a temp copy of the clip."""
    from app.config import settings
    from app.services import progress
    from app.services.vision import run_vision_analysis

    with (
        tempfile.TemporaryDirectory() as tmp,
        mock.patch.object(progress, "_get_redis", return_value=_NullRedis()),
        mock.patch.multiple(settings, **GOLDEN_SETTINGS),
    ):
        work = Path(tmp) / clip.name
        shutil.copy2(clip, work)
        return normalize(run_vision_analysis(str(work), SESSION_ID))


def main() -> int:
    if not CLIP.exists():
        print(f"no golden clip at {CLIP}", file=sys.stderr)
        return 1
    EXPECTED.write_text(json.dumps(run(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {EXPECTED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
