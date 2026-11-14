"""Label-free pose comparison metrics."""

import numpy as np
import pytest

from perf.pose_compare import (
    L_SHOULDER,
    L_WRIST,
    R_SHOULDER,
    R_WRIST,
    clip_metrics,
    largest_person,
)


def still_body(frames: int, wrist_noise: float, seed: int = 0) -> np.ndarray:
    """A motionless body with shoulders 100 px apart and noisy wrists."""
    rng = np.random.default_rng(seed)
    xy = np.zeros((frames, 17, 2))
    xy[:, L_SHOULDER] = (100.0, 100.0)
    xy[:, R_SHOULDER] = (200.0, 100.0)
    xy[:, L_WRIST] = (100.0, 200.0)
    xy[:, R_WRIST] = (200.0, 200.0)
    xy[:, [L_WRIST, R_WRIST]] += rng.normal(0.0, wrist_noise, (frames, 2, 2))
    return xy


def test_jitter_grows_with_wrist_noise_and_is_in_shoulder_widths() -> None:
    conf = np.full((200, 17), 0.9)
    seconds = np.full(195, 0.02)

    quiet = clip_metrics(still_body(200, 0.5), conf, seconds, fps=30.0)
    noisy = clip_metrics(still_body(200, 5.0), conf, seconds, fps=30.0)

    assert noisy["wrist_jitter_sw"] > 5 * quiet["wrist_jitter_sw"]
    assert quiet["wrist_jitter_sw"] < 0.05  # half a pixel of noise on a 100 px shoulder width
    assert quiet["fps"] == pytest.approx(50.0)
    assert quiet["person_found_share"] == 1.0
    assert quiet["both_wrists_confident_share"] == 1.0


def test_fast_body_motion_is_not_counted_as_jitter() -> None:
    xy = still_body(100, 0.0)
    xy[:, :, 0] += np.arange(100)[:, None] * 20.0  # the whole body slides 6 sw/s
    metrics = clip_metrics(xy, np.full((100, 17), 0.9), np.full(95, 0.02), fps=30.0)

    assert metrics["still_frames"] == 0
    assert np.isnan(metrics["wrist_jitter_sw"])


def test_wrist_confidence_shares() -> None:
    conf = np.full((10, 17), 0.9)
    conf[:4, L_WRIST] = 0.2
    metrics = clip_metrics(still_body(10, 0.0), conf, np.full(5, 0.02), fps=30.0)
    assert metrics["both_wrists_confident_share"] == pytest.approx(0.6)


def test_largest_person_and_nobody() -> None:
    small = np.zeros((133, 2))
    small[:17] = np.linspace(0, 10, 17)[:, None]
    big = np.zeros((133, 2))
    big[:17] = np.linspace(0, 300, 17)[:, None]
    scores = np.stack([np.full(133, 0.3), np.full(133, 0.8)])

    body, body_scores = largest_person(np.stack([small, big]), scores)

    assert body.shape == (17, 2) and body[-1, 0] == 300.0
    assert body_scores.shape == (17,) and body_scores[0] == 0.8

    nobody, no_scores = largest_person(np.zeros((0, 17, 2)), np.zeros((0, 17)))
    assert np.isnan(nobody).all() and not no_scores.any()
