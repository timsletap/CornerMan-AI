"""VIS-12: stance resolution and stance-aware strike classification."""

from __future__ import annotations

from functools import partial

import pytest
import synth
from synth import Punch

from app.vision import signals, stance, tracking
from app.vision.pipeline import analyze_poses, build_output_json
from app.vision.pose import Poses
from app.vision.types import LEFT_WRIST, RIGHT_WRIST

HANDS = {"left": LEFT_WRIST, "right": RIGHT_WRIST}


def _clip(punches: list[Punch], **kwargs: object) -> Poses:
    return synth.sequence(80, [synth.punching(80, punches, **kwargs)], track_ids=[1])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("profile", "hand", "expected", "role"),
    [
        ("orthodox", "left", "jab", "lead"),
        ("orthodox", "right", "cross", "rear"),
        ("southpaw", "left", "cross", "rear"),
        ("southpaw", "right", "jab", "lead"),
    ],
)
def test_straight_punch_is_jab_or_cross_by_lead_hand(
    profile: str, hand: str, expected: str, role: str
) -> None:
    poses = _clip([Punch(start=30, wrist=HANDS[hand], direction=(1.0, -0.2))])
    analysis = analyze_poses(poses, synth.config(), profile_stance=profile)
    assert [(s.hand, s.strike_type, s.hand_role) for s in analysis.strikes] == [
        (hand, expected, role)
    ]
    assert (analysis.stance_used, analysis.stance_source) == (profile, "profile")


def test_arm_extension_no_longer_decides_jab_versus_cross() -> None:
    """A short and a long straight from the lead hand are both jabs (v1 called long ones crosses)."""
    for reach in (0.7, 1.3):
        poses = _clip([Punch(start=30, wrist=LEFT_WRIST, reach=reach)])
        found = analyze_poses(poses, synth.config(), profile_stance="orthodox").strikes
        assert [s.strike_type for s in found] == ["jab"]


def test_hook_uppercut_and_body_shot() -> None:
    cfg = synth.config()
    hook = _clip([Punch(start=30, wrist=LEFT_WRIST, direction=(-1.0, 0.0), kind="bent")])
    assert [s.strike_type for s in analyze_poses(hook, cfg).strikes] == ["hook"]

    uppercut = _clip([Punch(start=30, wrist=RIGHT_WRIST, direction=(0.1, -1.0), kind="bent")])
    assert [s.strike_type for s in analyze_poses(uppercut, cfg).strikes] == ["uppercut"]

    body = _clip([Punch(start=30, wrist=RIGHT_WRIST, direction=(1.0, 0.1), wrist_start=(0.0, 1.0))])
    assert [s.strike_type for s in analyze_poses(body, cfg).strikes] == ["body_shot"]


def test_straight_punch_bent_at_its_velocity_peak_is_not_a_hook() -> None:
    """Sideways wrist travel with an elbow that straightens by full extension is a straight."""
    poses = _clip([Punch(start=30, wrist=RIGHT_WRIST, direction=(-1.0, 0.0))])
    found = analyze_poses(poses, synth.config(), profile_stance="orthodox").strikes
    assert [s.strike_type for s in found] == ["cross"]


def _side_signals(stance_name: str, facing: float) -> signals.Signals:
    cfg = synth.config()
    pose = partial(synth.side_fighter, stance=stance_name, facing=facing)
    poses = synth.sequence(60, [synth.punching(60, [], pose=pose, jitter_px=1.0)], track_ids=[1])
    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    return signals.build_signals(raw, poses.meta, cfg)


@pytest.mark.parametrize("stance_name", ["orthodox", "southpaw"])
@pytest.mark.parametrize("facing", [1.0, -1.0])
def test_auto_detect_from_a_side_view(stance_name: str, facing: float) -> None:
    assert stance.detect_stance(_side_signals(stance_name, facing)) == stance_name


def test_auto_detect_head_on_uses_the_foot_nearer_the_camera() -> None:
    cfg = synth.config()
    for lead_ankle, expected in ((synth.LEFT_ANKLE, "orthodox"), (synth.RIGHT_ANKLE, "southpaw")):
        frames = {}
        for f in range(40):
            kps = synth.fighter()
            kps[lead_ankle, 1] += 40  # lead foot is closer to the camera: lower in the image
            frames[f] = kps
        poses = synth.sequence(40, [frames], track_ids=[1])
        raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
        assert stance.detect_stance(signals.build_signals(raw, poses.meta, cfg)) == expected


def test_unclear_feet_fall_back_to_the_default() -> None:
    cfg = synth.config()
    poses = synth.sequence(40, [{f: synth.fighter() for f in range(40)}], track_ids=[1])
    raw = tracking.follow_target(poses.frames, poses.meta, cfg).frames
    sig = signals.build_signals(raw, poses.meta, cfg)
    assert stance.detect_stance(sig) is None
    assert stance.resolve_stance(sig) == ("orthodox", "default")
    assert stance.detect_stance(signals.build_signals([], poses.meta, cfg)) is None


def test_resolution_order_is_override_then_profile_then_detection() -> None:
    sig = _side_signals("southpaw", 1.0)
    assert stance.resolve_stance(sig, "orthodox", "southpaw") == ("orthodox", "override")
    assert stance.resolve_stance(sig, None, "orthodox") == ("orthodox", "profile")
    assert stance.resolve_stance(sig, None, "switch") == ("southpaw", "detected")
    assert stance.resolve_stance(sig, "nonsense", None) == ("southpaw", "detected")


def test_side_view_southpaw_jab_is_detected_and_named_end_to_end() -> None:
    """No profile: the stance is detected from the feet and the lead right hand jabs."""
    pose = partial(synth.side_fighter, stance="southpaw", facing=1.0)
    people = synth.punching(
        80, [Punch(start=40, wrist=RIGHT_WRIST, direction=(1.0, -0.1))], pose=pose
    )
    poses = synth.sequence(80, [people], track_ids=[1])
    analysis = analyze_poses(poses, synth.config())

    assert (analysis.stance_used, analysis.stance_source) == ("southpaw", "detected")
    assert [(s.hand, s.strike_type) for s in analysis.strikes] == [("right", "jab")]

    import uuid

    out = build_output_json(uuid.uuid4(), analysis, None, None)
    assert out["stance_used"] == "southpaw" and out["stance_source"] == "detected"
    assert out["strike_events"][0]["hand_role"] == "lead"


def test_hand_role() -> None:
    assert stance.hand_role("left", "orthodox") == "lead"
    assert stance.hand_role("right", "orthodox") == "rear"
    assert stance.hand_role("left", "southpaw") == "rear"
    assert stance.hand_role("right", "southpaw") == "lead"
