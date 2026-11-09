"""EVAL-02: CVAT XML <-> label JSON conversion, and the labeling guide's coverage."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import get_args

import pytest

from eval.cvat_to_labels import (
    ConversionError,
    cvat_to_labels,
    frame_to_ms,
    labels_to_cvat,
    main,
    ms_to_frame,
    snap_to_frames,
)
from eval.schema import ErrorType, Hand, Stance, StrikeType, Tag, Target, load_labels

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "eval" / "labels" / "samples"
SAMPLE_FILES = sorted(SAMPLES.glob("*.json"))


def xml(body: str, name: str = "clip_a.mp4") -> ET.Element:
    return ET.fromstring(
        f"<annotations><version>1.1</version><meta><task><name>{name}</name></task></meta>"
        f"{body}</annotations>"
    )


def strike(frame: int, hand: str = "left", kind: str = "jab", target: str = "head") -> str:
    return (
        f'<image id="{frame}" name="frame_{frame:06d}"><points label="strike" points="1,1">'
        f'<attribute name="hand">{hand}</attribute><attribute name="type">{kind}</attribute>'
        f'<attribute name="target">{target}</attribute></points></image>'
    )


def test_there_are_samples() -> None:
    assert len(SAMPLE_FILES) >= 2


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.stem)
def test_samples_round_trip_through_cvat(path: Path) -> None:
    original = load_labels(path)
    root = ET.fromstring(ET.tostring(labels_to_cvat(original)))
    back = cvat_to_labels(
        root,
        fps=original.fps,
        stance=original.fighter.stance,
        tags=original.tags,
        track_hint=original.fighter.track_hint,
        labeler=original.labeler,
        label_version=original.label_version,
    )
    assert back == original


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.stem)
def test_samples_round_trip_through_cli(path: Path, tmp_path: Path) -> None:
    original = load_labels(path)
    cvat_file = tmp_path / "export.xml"
    assert main(["to-cvat", str(path), "--out", str(cvat_file)]) == 0
    args = ["to-labels", str(cvat_file), "--fps", str(original.fps)]
    args += ["--stance", original.fighter.stance, "--tags", ",".join(original.tags)]
    args += ["--track-hint", original.fighter.track_hint or "", "--out", str(tmp_path / "out")]
    assert main(args) == 0
    assert load_labels(tmp_path / "out" / path.name) == original


@pytest.mark.parametrize("fps", [24.0, 25.0, 29.97, 30.0, 59.94, 60.0])
def test_frame_time_round_trip(fps: float) -> None:
    for frame in range(0, 2000, 7):
        assert ms_to_frame(frame_to_ms(frame, fps), fps) == frame


def test_off_frame_times_snap_to_the_nearest_frame() -> None:
    labels = load_labels(SAMPLES / "sample_bag_orthodox.json")
    moved = labels.model_copy(
        update={"strikes": [labels.strikes[0].model_copy(update={"t_ms": 1210})], "errors": []}
    )
    assert snap_to_frames(moved).strikes[0].t_ms == 1200
    assert snap_to_frames(labels) == labels


def test_clip_id_defaults_to_task_name_without_extension() -> None:
    labels = cvat_to_labels(xml(strike(30)), fps=30, stance="orthodox")
    assert labels.clip_id == "clip_a"
    assert labels.strikes[0].t_ms == 1000


def test_video_format_tracks_use_first_visible_frame() -> None:
    track = (
        '<track id="0" label="strike">'
        '<points frame="45" outside="0" points="1,1"><attribute name="hand">right</attribute>'
        '<attribute name="type">cross</attribute><attribute name="target">body</attribute>'
        '</points><points frame="46" outside="1" points="1,1"/></track>'
    )
    labels = cvat_to_labels(xml(track), fps=30, stance="orthodox")
    assert [(s.t_ms, s.hand, s.type, s.target) for s in labels.strikes] == [
        (1500, "right", "cross", "body")
    ]


def test_unknown_cvat_label_is_rejected() -> None:
    body = '<image id="3" name="f"><box label="kick"/></image>'
    with pytest.raises(ConversionError, match="unknown CVAT label 'kick' at frame 3"):
        cvat_to_labels(xml(body), fps=30, stance="orthodox")


def test_missing_attribute_names_the_frame() -> None:
    body = '<image id="9" name="f"><points label="strike" points="1,1"/></image>'
    with pytest.raises(ConversionError, match="strike at frame 9 is missing attribute 'hand'"):
        cvat_to_labels(xml(body), fps=30, stance="orthodox")


def test_bad_enum_value_is_rejected() -> None:
    with pytest.raises(ConversionError, match="strikes.0.type"):
        cvat_to_labels(xml(strike(10, kind="haymaker")), fps=30, stance="orthodox")


def test_unpaired_skip_is_rejected() -> None:
    body = (
        '<image id="5" name="f"><points label="skip_start" points="1,1">'
        '<attribute name="reason">clinch</attribute></points></image>'
    )
    with pytest.raises(ConversionError, match="1 skip_start but 0 skip_end"):
        cvat_to_labels(xml(body), fps=30, stance="orthodox")


def test_missing_task_name_needs_clip_id() -> None:
    root = ET.fromstring(f"<annotations>{strike(1)}</annotations>")
    with pytest.raises(ConversionError, match="pass --clip-id"):
        cvat_to_labels(root, fps=30, stance="orthodox")
    assert cvat_to_labels(root, fps=30, stance="orthodox", clip_id="x").clip_id == "x"


def test_cli_reports_errors_with_exit_code_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<annotations><image id='1'><box label='kick'/></image></annotations>")
    args = ["to-labels", str(bad), "--fps", "30", "--stance", "orthodox", "--clip-id", "x"]
    assert main(args) == 1
    assert "unknown CVAT label" in capsys.readouterr().err


def test_cvat_label_spec_matches_the_schema_enums() -> None:
    spec = json.loads((ROOT / "eval" / "cvat_labels.json").read_text(encoding="utf-8"))
    values = {
        (label["name"], attr["name"]): tuple(attr["values"])
        for label in spec
        for attr in label["attributes"]
    }
    assert {label["name"] for label in spec} == {"strike", "error", "skip_start", "skip_end"}
    assert values[("strike", "hand")] == get_args(Hand)
    assert values[("strike", "type")] == get_args(StrikeType)
    assert values[("strike", "target")] == get_args(Target)
    assert values[("error", "hand")] == get_args(Hand)
    assert values[("error", "type")] == get_args(ErrorType)


def test_labeling_guide_defines_every_enum_value() -> None:
    guide = (ROOT / "eval" / "LABELING.md").read_text(encoding="utf-8")
    enums = (StrikeType, ErrorType, Hand, Target, Tag, Stance)
    missing = [v for enum in enums for v in get_args(enum) if f"`{v}`" not in guide]
    assert missing == []
