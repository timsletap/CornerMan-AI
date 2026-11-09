"""VIS-09: target selection, following by track id, and re-acquisition."""

from __future__ import annotations

import numpy as np
import pytest
import synth

from app.vision import tracking
from app.vision.pipeline import analyze_poses
from app.vision.types import NOSE

FPS = int(synth.FPS)


def _nose_xs(track: tracking.TargetTrack) -> list[float]:
    return [fk.keypoints[NOSE][0] for fk in track.frames]


def test_selection_prefers_large_central_confident_person() -> None:
    cfg = synth.config()
    big = synth.fighter(cx=640, cy=250, sw=100)
    small = synth.fighter(cx=640, cy=250, sw=30)
    faint = synth.fighter(cx=640, cy=250, sw=150, conf=0.5)  # below occlusion threshold
    poses = synth.sequence(1, [{0: small}, {0: faint}, {0: big}], track_ids=[1, 2, 3])

    track = tracking.follow_target(poses.frames, poses.meta, cfg)

    assert track.target_track_id == 3
    assert len(track.frames) == 1
    assert track.frames[0].bbox_area == pytest.approx(
        (np.ptp(big[:, 0]) + 40) * (np.ptp(big[:, 1]) + 40), rel=1e-5
    )
    assert [t.track_id for t in track.tracks] == [1, 2, 3]


def test_selection_averages_over_the_window() -> None:
    """A big person seen for one frame loses to a smaller one present throughout."""
    steady = {f: synth.fighter(cx=640, sw=80) for f in range(60)}
    flash = {5: synth.fighter(cx=640, sw=200)}
    poses = synth.sequence(60, [steady, flash], track_ids=[1, 2])
    track = tracking.follow_target(poses.frames, poses.meta, synth.config())
    assert track.target_track_id == 1


def test_frames_without_a_confident_target_are_skipped() -> None:
    poses = synth.sequence(3, [{0: synth.fighter(), 2: synth.fighter(conf=0.3)}], track_ids=[1])
    track = tracking.follow_target(poses.frames, poses.meta, synth.config())
    assert [fk.frame_number for fk in track.frames] == [0]


def test_two_tracks_crossing_paths_never_switch() -> None:
    """The fighters swap sides; the target's id is even lost while they overlap."""
    n = 150
    lost = range(80, 90)
    a = {f: synth.fighter(cx=300 + 4 * f, sw=130) for f in range(n)}
    b = {f: synth.fighter(cx=980 - 4 * f, sw=70) for f in range(n)}  # they meet at f=85
    # The tracker drops A's id for 10 frames in the middle of the crossing, then
    # gives A a new one: B overlaps A's last box the whole time.
    a_ids = {f: (1 if f < lost.start else 7) for f in range(n) if f not in lost}
    a_seen = {f: kps for f, kps in a.items() if f in a_ids}
    poses = synth.sequence(n, [a_seen, b], track_ids=[a_ids, 2])

    track = tracking.follow_target(poses.frames, poses.meta, synth.config())

    assert track.target_track_id == 1
    assert track.identity_switches == 0
    xs = _nose_xs(track)
    assert len(xs) == n - len(lost)
    expected = [300 + 4 * f for f in range(n) if f not in lost]
    assert xs == pytest.approx(expected)  # always fighter A, never B
    assert track.handoffs == [(lost.stop, 1, 7)]


def test_target_reacquired_under_a_new_id_after_half_a_second() -> None:
    n = 90
    gap = range(30, 30 + FPS // 2)
    person = {f: synth.fighter(cx=600 + f) for f in range(n) if f not in gap}
    ids = {f: (4 if f < 30 else 9) for f in person}
    poses = synth.sequence(n, [person], track_ids=[ids])

    track = tracking.follow_target(poses.frames, poses.meta, synth.config())

    assert track.target_track_id == 4
    assert track.handoffs == [(45, 4, 9)]
    assert [fk.frame_number for fk in track.frames] == sorted(person)
    assert track.identity_switches == 0


def test_far_away_new_track_is_not_reacquired_by_overlap() -> None:
    """Soon after the target is lost, a new person elsewhere in frame is not them."""
    target = {f: synth.fighter(cx=300) for f in range(30)}
    stranger = {f: synth.fighter(cx=1000) for f in range(35, 50)}
    poses = synth.sequence(50, [target, stranger], track_ids=[1, 2])
    track = tracking.follow_target(poses.frames, poses.meta, synth.config())
    assert track.handoffs == []
    assert max(fk.frame_number for fk in track.frames) == 29


def test_target_returning_later_is_selected_again_but_bystanders_are_not() -> None:
    n = 200
    target_first = {f: synth.fighter(cx=640) for f in range(40)}
    target_back = {f: synth.fighter(cx=900) for f in range(120, n)}  # walked off, came back
    bystander = {f: synth.fighter(cx=150, sw=40) for f in range(n)}
    poses = synth.sequence(n, [target_first, bystander, target_back], track_ids=[1, 2, 3])

    track = tracking.follow_target(poses.frames, poses.meta, synth.config())

    assert track.handoffs == [(120, 1, 3)]
    assert 150.0 not in {round(x) for x in _nose_xs(track)}  # never the bystander


def test_requested_track_overrides_selection() -> None:
    big = {f: synth.fighter(cx=640, sw=100) for f in range(30)}
    small = {f: synth.fighter(cx=200, sw=50) for f in range(30)}
    poses = synth.sequence(30, [big, small], track_ids=[1, 2])
    cfg = synth.config()

    assert tracking.follow_target(poses.frames, poses.meta, cfg).target_track_id == 1
    chosen = tracking.follow_target(poses.frames, poses.meta, cfg, target_track_id=2)
    assert chosen.target_track_id == 2
    assert _nose_xs(chosen) == pytest.approx([200.0] * 30)
    # An id that is not in the clip falls back to automatic selection.
    assert tracking.follow_target(poses.frames, poses.meta, cfg, 99).target_track_id == 1

    assert analyze_poses(poses, cfg, target_track_id=2).target_track_id == 2


def test_detections_without_ids_are_tracked_by_overlap() -> None:
    walker = {f: synth.fighter(cx=300 + 4 * f) for f in range(60)}
    other = {f: synth.fighter(cx=1100, sw=50) for f in range(60)}
    poses = synth.sequence(60, [walker, other])  # no tracker ids

    track = tracking.follow_target(poses.frames, poses.meta, synth.config())

    assert len(track.frames) == 60
    assert len(track.tracks) == 2
    assert _nose_xs(track) == pytest.approx([300 + 4 * f for f in range(60)])


def test_teleporting_target_box_counts_as_identity_switch() -> None:
    """If the tracker itself swaps ids between two people, the jump is counted."""
    here = {f: synth.fighter(cx=300) for f in range(20)}
    there = {f: synth.fighter(cx=1000) for f in range(20, 40)}
    poses = synth.sequence(40, [here, there], track_ids=[1, 1])
    track = tracking.follow_target(poses.frames, poses.meta, synth.config())
    assert track.identity_switches == 1


def test_empty_poses() -> None:
    poses = synth.sequence(5, [])
    track = tracking.follow_target(poses.frames, poses.meta, synth.config())
    assert track.frames == [] and track.target_track_id is None


def test_iou() -> None:
    assert tracking.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert tracking.iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert tracking.iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)
