"""EVAL-04: metrics, the report model, and the eval runner on synthetic poses."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vision"))

import synth  # noqa: E402

from app.vision import pose  # noqa: E402
from app.vision.types import LEFT_WRIST, RIGHT_WRIST  # noqa: E402
from eval import metrics, run  # noqa: E402
from eval.metrics import PredError, PredStrike  # noqa: E402
from eval.report import Report  # noqa: E402
from eval.schema import ClipLabels  # noqa: E402


def _labels(strikes: list[dict[str, object]], **extra: object) -> ClipLabels:
    data: dict[str, object] = {
        "clip_id": "c1",
        "fps": 30,
        "tags": ["bag", "far"],
        "fighter": {"stance": "orthodox"},
        "strikes": strikes,
        "labeler": "test",
        "label_version": 1,
    }
    data.update(extra)
    return ClipLabels.model_validate(data)


def _strike(t_ms: int, hand: str, type_: str) -> dict[str, object]:
    return {"t_ms": t_ms, "hand": hand, "type": type_, "target": "head"}


def test_score_clip_counts_and_type_pairs() -> None:
    labels = _labels(
        [
            _strike(1000, "left", "jab"),
            _strike(2000, "right", "cross"),
            _strike(3000, "left", "hook"),
        ],
        errors=[{"t_ms": 2000, "type": "dropped_guard", "hand": "left"}],
    )
    preds = [
        PredStrike(1040, "left", "jab"),
        PredStrike(2100, "right", "jab"),  # right time, wrong type
        PredStrike(5000, "left", "hook"),  # nothing there
    ]
    errors = [PredError(2100, "left", "dropped_guard"), PredError(1040, "left", "chicken_wing")]
    score = metrics.score_clip(labels, preds, errors)

    assert (score.tp, score.fp, score.fn) == (2, 1, 1)
    assert sorted(score.type_pairs) == [("cross", "jab"), ("jab", "jab")]
    assert score.errors == {"dropped_guard": (1, 0, 0), "chicken_wing": (0, 1, 0)}
    assert score.strike_outcomes == [(0, True), (1, False), (2, False)]

    detection = metrics.detection([score])
    assert detection.precision == pytest.approx(0.6667, abs=1e-4)
    assert detection.recall == pytest.approx(0.6667, abs=1e-4)

    types = metrics.strike_type([score])
    assert types.per_class["jab"].recall == 1.0
    assert types.per_class["jab"].precision == 0.5
    assert types.per_class["cross"].f1 == 0.0
    assert types.per_class["hook"].support == 0  # the hook label was never matched
    assert types.macro_f1 == pytest.approx((0.6667 + 0.0) / 2, abs=1e-4)
    assert types.confusion.matrix[1][0] == 1  # cross labeled, jab predicted

    assert metrics.by_tag([score])["far"].detection_f1 == detection.f1


def test_predictions_in_skipped_spans_and_abstained_are_ignored() -> None:
    labels = _labels(
        [_strike(1000, "left", "jab")],
        notes=[{"start_ms": 4000, "end_ms": 6000, "reason": "clinch"}],
    )
    preds = [
        PredStrike(1000, "left", "jab"),
        PredStrike(5000, "right", "cross"),
        PredStrike(8000, "right", "cross", abstained=True),
    ]
    score = metrics.score_clip(labels, preds, [])
    assert (score.tp, score.fp, score.fn) == (1, 0, 0)


def test_other_typed_prediction_counts_against_recall() -> None:
    labels = _labels([_strike(1000, "left", "jab")])
    types = metrics.strike_type(
        [metrics.score_clip(labels, [PredStrike(1000, "left", "other")], [])]
    )
    assert types.per_class["jab"].support == 1
    assert types.per_class["jab"].recall == 0.0
    assert types.confusion.unclassified[0] == 1


def _poses(n_frames: int = 150, seed: int = 0) -> pose.Poses:
    """One fighter punching once a second with alternating hands, plus jitter."""
    rng = np.random.default_rng(seed)
    offsets = synth.punch_offsets()
    frames: dict[int, np.ndarray] = {}
    for f in range(n_frames):
        kps = synth.fighter()
        k = f % 30
        if k < len(offsets):
            wrist = LEFT_WRIST if (f // 30) % 2 == 0 else RIGHT_WRIST
            kps[wrist, 1] -= offsets[k] * 60
            kps[wrist, 0] += offsets[k] * 40
        kps[:, :2] += rng.normal(0, 0.5, size=(17, 2))
        frames[f] = kps
    return synth.sequence(n_frames, [frames])


@pytest.fixture
def clip_dir(tmp_path: Path) -> Path:
    """A clips+labels dir holding one cached-poses clip labeled from a pipeline run."""
    cfg = synth.config()
    poses = _poses()
    pose.write_poses(poses, tmp_path / "c1_poses.parquet", cfg)
    found, _ = run.predictions(run.analyze_poses(poses, cfg))
    assert len(found) >= 4
    strikes = [_strike(s.t_ms + 33, s.hand, s.type) for s in found]
    strikes.append(_strike(found[-1].t_ms + 2000, "left", "jab"))  # one the pipeline misses
    labels = _labels(strikes)
    (tmp_path / "c1.json").write_text(labels.model_dump_json(), encoding="utf-8")
    return tmp_path


def test_evaluate_from_cached_poses(clip_dir: Path) -> None:
    cfg = synth.config()
    report, runs = run.evaluate("dev", ["c1"], clip_dir, clip_dir, cfg, from_cache=True)

    assert report.detection.fn == 1
    assert report.detection.fp == 0
    assert report.detection.tp == len(runs[0].strikes)
    assert report.strike_type.macro_f1 == 1.0
    assert report.identity_switches is not None
    assert report.identity_switches.per_clip == {"c1": 0}
    assert report.throughput.stage1_x_realtime is None  # poses came from the cache
    assert report.throughput.stages23_x_realtime is not None
    assert report.config_hash.startswith("sha256:")
    assert set(report.by_tag) == {"bag", "far"}


def test_report_round_trips_and_is_deterministic(clip_dir: Path, tmp_path: Path) -> None:
    cfg = synth.config()
    first, _ = run.evaluate("dev", ["c1"], clip_dir, clip_dir, cfg, from_cache=True)
    second, _ = run.evaluate("dev", ["c1"], clip_dir, clip_dir, cfg, from_cache=True)
    assert first.metrics() == second.metrics()

    out = tmp_path / "reports" / "r.json"
    run.write_report(first, out)
    loaded = Report.model_validate(json.loads(out.read_text(encoding="utf-8")))
    assert loaded.metrics() == first.metrics()
    assert "strikes" in run.format_report(loaded)


def test_config_change_changes_hash() -> None:
    assert run.config_hash(synth.config()) != run.config_hash(
        synth.config(strike_velocity_threshold=2.0)
    )


def test_missing_inputs_are_reported(clip_dir: Path) -> None:
    cfg = synth.config()
    with pytest.raises(run.EvalError, match="no label file"):
        run.evaluate("dev", ["nope"], clip_dir, clip_dir, cfg)
    (clip_dir / "c2.json").write_text(_labels([], clip_id="c2").model_dump_json(), encoding="utf-8")
    with pytest.raises(run.EvalError, match="no usable poses"):
        run.evaluate("dev", ["c2"], clip_dir, clip_dir, cfg)
    with pytest.raises(run.EvalError, match="has no clips"):
        run.evaluate("dev", [], clip_dir, clip_dir, cfg)


def test_cli_fails_cleanly_on_empty_split(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    splits = tmp_path / "splits.yaml"
    splits.write_text("dev: []\ntest: []\n", encoding="utf-8")
    assert run.main(["--split", "dev", "--splits", str(splits)]) == 2
    assert "has no clips" in capsys.readouterr().err
