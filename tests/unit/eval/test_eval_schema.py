"""EVAL-01: label and split validation."""

import json
from pathlib import Path
from typing import Any

import pytest

from eval.schema import main, validate_label_file, validate_labels_dir, validate_splits_file

SAMPLES = Path(__file__).resolve().parents[3] / "eval" / "labels" / "samples"


def sample(name: str = "sample_bag_orthodox") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SAMPLES / f"{name}.json").read_text())
    return data


def write_label(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / f"{data['clip_id']}.json"
    path.write_text(json.dumps(data))
    return path


def write_splits(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "splits.yaml"
    path.write_text(text)
    return path


def test_committed_samples_validate() -> None:
    assert validate_labels_dir(SAMPLES) == []


def test_cli_validate_samples_exit_zero() -> None:
    assert main(["validate", str(SAMPLES)]) == 0


def test_unknown_strike_type_names_file_index_and_value(tmp_path: Path) -> None:
    data = sample()
    data["strikes"][2]["type"] = "spinning_backfist"
    path = write_label(tmp_path, data)

    problems = validate_label_file(path)

    assert len(problems) == 1
    assert str(path) in problems[0]
    assert "strikes[2].type" in problems[0]
    assert "'spinning_backfist'" in problems[0]


@pytest.mark.parametrize(
    ("field", "value"),
    [("hand", "both"), ("target", "legs")],
)
def test_other_strike_enums_rejected(tmp_path: Path, field: str, value: str) -> None:
    data = sample()
    data["strikes"][0][field] = value
    problems = validate_label_file(write_label(tmp_path, data))
    assert any(f"strikes[0].{field}" in p and repr(value) in p for p in problems)


def test_unknown_stance_tag_and_error_type_rejected(tmp_path: Path) -> None:
    data = sample()
    data["fighter"]["stance"] = "switch"
    data["tags"].append("underwater")
    data["errors"][0]["type"] = "flat_feet"
    problems = validate_label_file(write_label(tmp_path, data))
    joined = "\n".join(problems)
    assert "fighter.stance" in joined
    assert "tags[4]" in joined
    assert "errors[0].type" in joined


def test_unsorted_strikes_rejected(tmp_path: Path) -> None:
    data = sample()
    data["strikes"][0], data["strikes"][1] = data["strikes"][1], data["strikes"][0]
    problems = validate_label_file(write_label(tmp_path, data))
    assert any("sorted" in p for p in problems)


def test_duplicate_hand_and_time_rejected(tmp_path: Path) -> None:
    data = sample()
    data["strikes"].insert(1, dict(data["strikes"][0], type="hook"))
    problems = validate_label_file(write_label(tmp_path, data))
    assert any("duplicate strike" in p for p in problems)


def test_same_time_different_hands_allowed(tmp_path: Path) -> None:
    data = sample()
    data["strikes"].insert(1, {"t_ms": 1200, "hand": "right", "type": "cross", "target": "head"})
    assert validate_label_file(write_label(tmp_path, data)) == []


def test_unknown_field_rejected(tmp_path: Path) -> None:
    data = sample()
    data["strikes"][0]["tme_ms"] = 5
    problems = validate_label_file(write_label(tmp_path, data))
    assert any("strikes[0].tme_ms" in p for p in problems)


def test_clip_id_must_match_file_name(tmp_path: Path) -> None:
    path = tmp_path / "other_name.json"
    path.write_text(json.dumps(sample()))
    assert any("does not match file name" in p for p in validate_label_file(path))


def test_t_ms_past_clip_end_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "sample_bag_orthodox.mp4").write_bytes(b"")
    monkeypatch.setattr("eval.schema.clip_duration_ms", lambda _path: 3000)
    problems = validate_label_file(write_label(tmp_path, sample()), clips_dir=clips)
    assert any("past the end" in p for p in problems)


def test_t_ms_check_skipped_when_clip_absent(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    assert validate_label_file(write_label(tmp_path, sample()), clips_dir=clips) == []


def test_invalid_json_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    assert any("invalid JSON" in p for p in validate_label_file(path))


VALID_SPLITS = """
dev: [a, b]
test: [c]
seed: [a]
fighters: {a: F01, b: F02, c: F03}
"""


def test_valid_splits_pass(tmp_path: Path) -> None:
    assert validate_splits_file(write_splits(tmp_path, VALID_SPLITS)) == []


def test_committed_splits_file_validates() -> None:
    assert validate_splits_file(SAMPLES.parents[1] / "splits.yaml") == []


def test_same_fighter_in_dev_and_test_fails(tmp_path: Path) -> None:
    path = write_splits(tmp_path, VALID_SPLITS.replace("c: F03", "c: F01"))
    problems = validate_splits_file(path)
    assert any("fighters in both dev and test" in p and "F01" in p for p in problems)
    assert main(["validate-splits", str(path)]) == 1


def test_clip_in_both_dev_and_test_fails(tmp_path: Path) -> None:
    path = write_splits(tmp_path, VALID_SPLITS.replace("test: [c]", "test: [c, b]"))
    assert any("both dev and test" in p for p in validate_splits_file(path))


def test_seed_outside_dev_fails(tmp_path: Path) -> None:
    path = write_splits(tmp_path, VALID_SPLITS.replace("seed: [a]", "seed: [c]"))
    assert any("seed clips must also be in dev" in p for p in validate_splits_file(path))


def test_clip_without_fighter_fails(tmp_path: Path) -> None:
    path = write_splits(tmp_path, VALID_SPLITS.replace(", c: F03", ""))
    assert any("missing from fighters" in p for p in validate_splits_file(path))


def test_splits_reports_unlabeled_clips(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "a.json").write_text("{}")
    problems = validate_splits_file(write_splits(tmp_path, VALID_SPLITS), labels_dir=labels)
    assert any("no label file" in p and "'b'" in p for p in problems)
