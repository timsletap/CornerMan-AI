"""Metrics over matched predictions and labels (EVAL-04). Pure functions, no I/O."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from eval.match import DEFAULT_WINDOW_MS, match_events
from eval.report import ClassScore, Confusion, Detection, StrikeType, TagScore
from eval.schema import ERROR_TYPES, STRIKE_TYPES, ClipLabels


@dataclass(frozen=True)
class PredStrike:
    t_ms: int
    """Predicted strike time, ms from video start."""
    hand: str
    type: str
    confidence: float | None = None
    abstained: bool = False


@dataclass(frozen=True)
class PredError:
    t_ms: int
    """Time of the strike the flag belongs to, ms from video start."""
    hand: str
    """dropped_guard: the hand that dropped (off hand); chicken_wing: the punching hand."""
    type: str
    confidence: float | None = None


@dataclass
class ClipScore:
    """Counts for one clip."""

    clip_id: str
    tags: list[str]
    tp: int = 0
    fp: int = 0
    fn: int = 0
    type_pairs: list[tuple[str, str]] = field(default_factory=list)
    """(label type, predicted type) for each matched strike."""
    errors: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    """error type -> (tp, fp, fn)"""
    strike_outcomes: list[tuple[int, bool]] = field(default_factory=list)
    """(index into the clip's predicted strikes, matched a label with the right type)."""


def _ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def prf(tp: int, fp: int, fn: int) -> Detection:
    return Detection(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=round(_ratio(tp, tp + fp), 4),
        recall=round(_ratio(tp, tp + fn), 4),
        f1=round(_ratio(2 * tp, 2 * tp + fp + fn), 4),
    )


def _outside_skipped(labels: ClipLabels, t_ms: int) -> bool:
    return not any(n.start_ms <= t_ms <= n.end_ms for n in labels.notes)


def score_clip(
    labels: ClipLabels,
    strikes: Sequence[PredStrike],
    errors: Sequence[PredError],
    window_ms: int = DEFAULT_WINDOW_MS,
) -> ClipScore:
    """Match one clip's predictions to its labels.

    Predictions inside a span the labeler skipped (``notes``) are ignored: there is no
    ground truth there, so they are neither right nor wrong. Abstained strikes are not
    predictions and are ignored too. ``window_ms`` is in ms.
    """
    score = ClipScore(clip_id=labels.clip_id, tags=list(labels.tags))
    kept = [
        (i, s)
        for i, s in enumerate(strikes)
        if not s.abstained and _outside_skipped(labels, s.t_ms)
    ]
    result = match_events([s for _, s in kept], labels.strikes, window_ms)
    score.tp, score.fp, score.fn = result.tp, result.fp, result.fn
    correct: dict[int, bool] = {i: False for i, _ in kept}
    for m in result.matches:
        orig, pred = kept[m.pred_index]
        truth = labels.strikes[m.label_index].type
        score.type_pairs.append((truth, pred.type))
        correct[orig] = truth == pred.type
    score.strike_outcomes = sorted(correct.items())
    for error_type in ERROR_TYPES:
        preds = [e for e in errors if e.type == error_type and _outside_skipped(labels, e.t_ms)]
        truth_errors = [e for e in labels.errors if e.type == error_type]
        r = match_events(preds, truth_errors, window_ms)
        score.errors[error_type] = (r.tp, r.fp, r.fn)
    return score


def detection(scores: Sequence[ClipScore]) -> Detection:
    return prf(sum(s.tp for s in scores), sum(s.fp for s in scores), sum(s.fn for s in scores))


def strike_type(scores: Sequence[ClipScore]) -> StrikeType:
    """Per-type scores and the confusion matrix, on matched pairs only."""
    labels = list(STRIKE_TYPES)
    index = {name: i for i, name in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    unclassified = [0] * len(labels)
    for s in scores:
        for truth, pred in s.type_pairs:
            if pred in index:
                matrix[index[truth]][index[pred]] += 1
            else:
                unclassified[index[truth]] += 1

    per_class: dict[str, ClassScore] = {}
    for name, i in index.items():
        tp = matrix[i][i]
        support = sum(matrix[i]) + unclassified[i]
        predicted = sum(row[i] for row in matrix)
        precision, recall = _ratio(tp, predicted), _ratio(tp, support)
        per_class[name] = ClassScore(
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(_ratio(2 * precision * recall, precision + recall), 4),
            support=support,
        )
    present = [c.f1 for c in per_class.values() if c.support > 0]
    return StrikeType(
        macro_f1=round(_ratio(sum(present), len(present)), 4),
        per_class=per_class,
        confusion=Confusion(labels=labels, matrix=matrix, unclassified=unclassified),
    )


def errors(scores: Sequence[ClipScore]) -> dict[str, Detection]:
    out: dict[str, Detection] = {}
    for error_type in ERROR_TYPES:
        counts = [s.errors.get(error_type, (0, 0, 0)) for s in scores]
        out[error_type] = prf(
            sum(c[0] for c in counts), sum(c[1] for c in counts), sum(c[2] for c in counts)
        )
    return out


def by_tag(scores: Sequence[ClipScore]) -> dict[str, TagScore]:
    out: dict[str, TagScore] = {}
    for tag in sorted({t for s in scores for t in s.tags}):
        tagged = [s for s in scores if tag in s.tags]
        d = detection(tagged)
        out[tag] = TagScore(
            clips=len(tagged),
            detection_f1=d.f1,
            detection_precision=d.precision,
            detection_recall=d.recall,
        )
    return out
