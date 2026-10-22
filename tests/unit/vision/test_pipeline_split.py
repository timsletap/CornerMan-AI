"""VIS-08: stage boundaries, poses cache, and rerun speed."""

import ast
import time
from pathlib import Path

import numpy as np
import pytest
import synth

from app.vision import pose, tracking
from app.vision.pipeline import analyze_poses
from app.vision.types import LEFT_WRIST, RIGHT_WRIST, VideoMeta, poses_cache_path

VISION_DIR = Path(__file__).resolve().parents[3] / "backend" / "app" / "vision"
PURE_MODULES = ["signals.py", "strikes.py", "errors.py", "tracking.py"]
FORBIDDEN = (
    "app.database",
    "app.models",
    "app.tasks",
    "app.services",
    "app.api",
    "celery",
    "sqlalchemy",
    "redis",
)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_stages_do_not_import_db_queue_or_progress(module: str) -> None:
    bad = {n for n in _imports(VISION_DIR / module) if n.startswith(FORBIDDEN)}
    assert bad == set(), f"{module} imports {sorted(bad)}"


def _sparring(n_frames: int, seed: int = 0) -> pose.Poses:
    """A fighter throwing a punch every second, a smaller bystander, and pose jitter."""
    rng = np.random.default_rng(seed)
    target: dict[int, np.ndarray] = {}
    bystander: dict[int, np.ndarray] = {}
    offsets = synth.punch_offsets()
    for f in range(n_frames):
        kps = synth.fighter()
        k = f % 30
        if k < len(offsets):
            wrist = LEFT_WRIST if (f // 30) % 2 == 0 else RIGHT_WRIST
            kps[wrist, 1] -= offsets[k] * 60  # punch toward the camera's up-axis
            kps[wrist, 0] += offsets[k] * 40
        kps[:, :2] += rng.normal(0, 1.0, size=(17, 2))
        target[f] = kps
        bystander[f] = synth.fighter(cx=200, cy=300, sw=40)
    return synth.sequence(n_frames, [target, bystander])


def test_rerun_from_cache_is_fast_for_60s(tmp_path: Path) -> None:
    cfg = synth.config()
    poses = _sparring(int(60 * synth.FPS))
    cache = tmp_path / "clip_poses.parquet"
    pose.write_poses(poses, cache, cfg)

    start = time.perf_counter()
    loaded = pose.read_poses(cache, cfg, poses.meta)
    assert loaded is not None
    analysis = analyze_poses(loaded, cfg)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"stages 2-3 from cache took {elapsed:.2f}s"
    assert len(analysis.frames) == 1800
    assert len(analysis.strikes) >= 50  # one punch per second is found


def test_cache_round_trip_is_exact(tmp_path: Path) -> None:
    cfg = synth.config()
    poses = _sparring(90, seed=3)
    cache = tmp_path / "p.parquet"
    pose.write_poses(poses, cache, cfg)

    loaded = pose.read_poses(cache, cfg, poses.meta)

    assert loaded is not None
    assert loaded.frames.equals(poses.frames) or (
        loaded.frames.to_dict("list") == poses.frames.to_dict("list")
    )
    assert analyze_poses(loaded, cfg) == analyze_poses(poses, cfg)


@pytest.mark.parametrize(
    "change",
    [
        {"cfg": {"frame_skip": 2}},
        {"cfg": {"model_name": "yolov8n-pose.pt"}},
        {"meta": {"total_frames": 91}},
        {"meta": {"fps": 25.0}},
    ],
    ids=["frame_skip", "model", "video_length", "fps"],
)
def test_cache_is_ignored_when_inputs_change(
    tmp_path: Path, change: dict[str, dict[str, object]]
) -> None:
    cfg = synth.config()
    poses = _sparring(90)
    cache = tmp_path / "p.parquet"
    pose.write_poses(poses, cache, cfg)

    meta_values = {**poses.meta.__dict__, **change.get("meta", {})}
    other_cfg = synth.config(**change.get("cfg", {}))
    assert pose.read_poses(cache, other_cfg, VideoMeta(**meta_values)) is None  # type: ignore[arg-type]


def test_corrupt_or_missing_cache_is_ignored(tmp_path: Path) -> None:
    cfg = synth.config()
    meta = VideoMeta(fps=30.0, total_frames=10, width=1280, height=720)
    assert pose.read_poses(tmp_path / "missing.parquet", cfg, meta) is None
    bad = tmp_path / "bad.parquet"
    bad.write_bytes(b"not parquet")
    assert pose.read_poses(bad, cfg, meta) is None


def test_model_path_does_not_invalidate_cache(tmp_path: Path) -> None:
    """Same weights file in a different directory (e.g. Docker /opt/models) reuses it."""
    poses = _sparring(30)
    cache = tmp_path / "p.parquet"
    pose.write_poses(poses, cache, synth.config(model_name="yolov8m-pose.pt"))
    other = synth.config(model_name="/opt/models/yolov8m-pose.pt")
    assert pose.read_poses(cache, other, poses.meta) is not None


def test_cache_lives_next_to_video() -> None:
    assert poses_cache_path("/data/videos/u/abc.mp4") == Path("/data/videos/u/abc_poses.parquet")


def test_primary_actor_prefers_large_central_confident_person() -> None:
    cfg = synth.config()
    big = synth.fighter(cx=640, cy=250, sw=100)
    small = synth.fighter(cx=640, cy=250, sw=30)
    faint = synth.fighter(cx=640, cy=250, sw=150, conf=0.5)  # below occlusion threshold
    poses = synth.sequence(1, [{0: small}, {0: faint}, {0: big}])

    track = tracking.primary_track(poses.frames, poses.meta, cfg)

    assert len(track) == 1
    assert track[0].keypoints[0][0] == pytest.approx(640, abs=0.01)
    assert track[0].bbox_area == pytest.approx(
        (big[:, 0].ptp() + 40) * (big[:, 1].ptp() + 40), rel=1e-5
    )


def test_frames_without_a_confident_person_are_skipped() -> None:
    poses = synth.sequence(3, [{0: synth.fighter(), 2: synth.fighter(conf=0.3)}])
    track = tracking.primary_track(poses.frames, poses.meta, synth.config())
    assert [fk.frame_number for fk in track] == [0]
