"""One-to-one matching of predicted events to labeled events (EVAL-03).

A prediction matches a label when both use the same ``hand`` and
``|t_pred - t_label| <= window_ms``. All candidate pairs are sorted by time distance
(ascending) and assigned greedily; each label and each prediction is used at most once.
Unmatched predictions are false positives, unmatched labels are false negatives.
Strikes and error flags both use this rule, each with their own hand field.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

DEFAULT_WINDOW_MS = 150


class TimedEvent(Protocol):
    """Anything with a time in ms from video start and an anatomical hand."""

    @property
    def t_ms(self) -> int: ...

    @property
    def hand(self) -> str: ...


@dataclass(frozen=True)
class Match:
    pred_index: int
    label_index: int
    delta_ms: int
    """Absolute time difference between prediction and label, ms."""


@dataclass(frozen=True)
class MatchResult:
    matches: list[Match]
    unmatched_preds: list[int]
    unmatched_labels: list[int]

    @property
    def tp(self) -> int:
        return len(self.matches)

    @property
    def fp(self) -> int:
        return len(self.unmatched_preds)

    @property
    def fn(self) -> int:
        return len(self.unmatched_labels)


def match_events(
    preds: Sequence[TimedEvent],
    labels: Sequence[TimedEvent],
    window_ms: int = DEFAULT_WINDOW_MS,
) -> MatchResult:
    """Match predictions to labels one-to-one.

    Args:
        preds: predicted events (``t_ms`` in ms, ``hand`` left/right).
        labels: ground-truth events, same units.
        window_ms: maximum allowed time difference in ms, inclusive.

    Ties in time distance are broken by label index, then prediction index, so the
    result is deterministic.
    """
    if window_ms < 0:
        raise ValueError(f"window_ms must be >= 0, got {window_ms}")

    candidates = sorted(
        (abs(p.t_ms - lab.t_ms), li, pi)
        for pi, p in enumerate(preds)
        for li, lab in enumerate(labels)
        if p.hand == lab.hand and abs(p.t_ms - lab.t_ms) <= window_ms
    )

    used_preds: set[int] = set()
    used_labels: set[int] = set()
    matches: list[Match] = []
    for delta, li, pi in candidates:
        if pi in used_preds or li in used_labels:
            continue
        used_preds.add(pi)
        used_labels.add(li)
        matches.append(Match(pred_index=pi, label_index=li, delta_ms=delta))

    matches.sort(key=lambda m: m.label_index)
    return MatchResult(
        matches=matches,
        unmatched_preds=[i for i in range(len(preds)) if i not in used_preds],
        unmatched_labels=[i for i in range(len(labels)) if i not in used_labels],
    )
