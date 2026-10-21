"""EVAL-03: one-to-one prediction/label matching."""

from dataclasses import dataclass

import pytest

from eval.match import Match, match_events
from eval.schema import StrikeLabel


@dataclass(frozen=True)
class Ev:
    t_ms: int
    hand: str = "left"


def test_exact_match() -> None:
    r = match_events([Ev(1000)], [Ev(1000)])
    assert r.matches == [Match(pred_index=0, label_index=0, delta_ms=0)]
    assert (r.tp, r.fp, r.fn) == (1, 0, 0)


@pytest.mark.parametrize("offset", [150, -150])
def test_150ms_matches(offset: int) -> None:
    assert match_events([Ev(1000 + offset)], [Ev(1000)]).tp == 1


@pytest.mark.parametrize("offset", [151, -151])
def test_151ms_does_not_match(offset: int) -> None:
    r = match_events([Ev(1000 + offset)], [Ev(1000)])
    assert (r.tp, r.fp, r.fn) == (0, 1, 1)


def test_two_predictions_competing_closer_wins() -> None:
    r = match_events([Ev(1100), Ev(1020)], [Ev(1000)])
    assert r.matches == [Match(pred_index=1, label_index=0, delta_ms=20)]
    assert r.unmatched_preds == [0]
    assert (r.tp, r.fp, r.fn) == (1, 1, 0)


def test_wrong_hand_never_matches() -> None:
    r = match_events([Ev(1000, "right")], [Ev(1000, "left")])
    assert (r.tp, r.fp, r.fn) == (0, 1, 1)


def test_empty_predictions() -> None:
    r = match_events([], [Ev(1000), Ev(2000)])
    assert (r.tp, r.fp, r.fn) == (0, 0, 2)
    assert r.unmatched_labels == [0, 1]


def test_empty_labels() -> None:
    r = match_events([Ev(1000)], [])
    assert (r.tp, r.fp, r.fn) == (0, 1, 0)


def test_greedy_global_assignment_prefers_closest_pair_first() -> None:
    # pred 0 is 40 ms from label 0 and 60 ms from label 1; pred 1 is 10 ms from label 0.
    # Closest pair (pred1, label0) is taken first, so pred 0 falls back to label 1.
    r = match_events([Ev(1040), Ev(1010)], [Ev(1000), Ev(1100)])
    assert {(m.pred_index, m.label_index) for m in r.matches} == {(1, 0), (0, 1)}


def test_ties_are_deterministic() -> None:
    r = match_events([Ev(1050), Ev(950)], [Ev(1000)])
    assert r.matches == [Match(pred_index=0, label_index=0, delta_ms=50)]


def test_custom_window() -> None:
    assert match_events([Ev(1200)], [Ev(1000)], window_ms=200).tp == 1
    assert match_events([Ev(1200)], [Ev(1000)], window_ms=199).tp == 0


def test_negative_window_rejected() -> None:
    with pytest.raises(ValueError):
        match_events([], [], window_ms=-1)


def test_works_with_label_models() -> None:
    label = StrikeLabel(t_ms=1000, hand="left", type="jab", target="head")
    assert match_events([Ev(1100)], [label]).tp == 1
