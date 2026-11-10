"""Stance resolution (VIS-12): which hand leads.

A jab is the lead hand's straight punch and a cross the rear hand's, so classification
needs the stance. It comes from, in order: an override on the analyze request, the
fighter's profile, auto-detection from the footage, and finally a default.

Pure functions: no I/O, database, task queue, or progress reporting.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from app.vision.signals import Signals
from app.vision.types import LEFT_ANKLE, NOSE, RIGHT_ANKLE

Stance = Literal["orthodox", "southpaw"]
StanceSource = Literal["override", "profile", "detected", "default"]
HandRole = Literal["lead", "rear"]

STANCES: tuple[str, ...] = ("orthodox", "southpaw")
DEFAULT_STANCE: Stance = "orthodox"

DETECT_SECONDS = 3.0
"""Seconds at the start of the clip used for auto-detection."""

SIDE_VIEW_MIN_SW = 0.15
"""Nose offset from the shoulder midpoint (sw, along x) above which the fighter is
taken to face sideways in the image."""

ANKLE_MARGIN_SW = 0.15
"""Minimum ankle separation along the facing direction (sw) to call a lead foot."""

MIN_FRAMES = 5


def hand_role(hand: str, stance: str) -> HandRole:
    """``lead`` or ``rear`` for an anatomical hand: orthodox leads with the left."""
    lead_hand = "left" if stance == "orthodox" else "right"
    return "lead" if hand == lead_hand else "rear"


def detect_stance(sig: Signals) -> Stance | None:
    """Stance from the feet over the first ``DETECT_SECONDS``, or None when unclear.

    The lead foot is the one farther forward along the direction the fighter faces.
    In a side or three-quarter view the facing direction is where the nose sits
    relative to the shoulders, and "forward" is along the image x axis. Head-on to the
    camera, "forward" is toward the camera: the lead foot is lower in the image.
    """
    if len(sig) == 0:
        return None
    window = sig.t_s <= sig.t_s[0] + DETECT_SECONDS
    usable = window & sig.ok(LEFT_ANKLE) & sig.ok(RIGHT_ANKLE) & sig.ok(NOSE)
    if int(usable.sum()) < MIN_FRAMES:
        return None

    nose_x = float(np.median(sig.rel[usable, NOSE, 0]))
    left = sig.rel[usable, LEFT_ANKLE]
    right = sig.rel[usable, RIGHT_ANKLE]
    if abs(nose_x) >= SIDE_VIEW_MIN_SW:
        facing = 1.0 if nose_x > 0 else -1.0
        left_ahead = float(np.median((left[:, 0] - right[:, 0]) * facing))
    else:
        left_ahead = float(np.median(left[:, 1] - right[:, 1]))  # nearer the camera = lower

    if left_ahead > ANKLE_MARGIN_SW:
        return "orthodox"
    if left_ahead < -ANKLE_MARGIN_SW:
        return "southpaw"
    return None


def _known(value: str | None) -> Stance | None:
    if value == "orthodox":
        return "orthodox"
    if value == "southpaw":
        return "southpaw"
    return None


def resolve_stance(
    sig: Signals, override: str | None = None, profile: str | None = None
) -> tuple[Stance, StanceSource]:
    """The stance to classify with and where it came from.

    ``override`` and ``profile`` count only when they are ``orthodox`` or ``southpaw``
    (a ``switch`` or unknown profile falls through to detection).
    """
    chosen = _known(override)
    if chosen is not None:
        return chosen, "override"
    chosen = _known(profile)
    if chosen is not None:
        return chosen, "profile"
    detected = detect_stance(sig)
    if detected is not None:
        return detected, "detected"
    return DEFAULT_STANCE, "default"
