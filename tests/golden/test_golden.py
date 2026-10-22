"""QA-02: the vision pipeline's output on the golden clip must not change unintentionally."""

import json
import shutil

import pytest
from golden import CLIP, EXPECTED, run  # tests/golden is on sys.path (pytest rootdir mode)

pytestmark = [
    pytest.mark.skipif(
        not CLIP.exists(),
        reason=f"golden clip missing: add a 5 s clip (own or CC footage) at {CLIP}",
    ),
    pytest.mark.skipif(
        not EXPECTED.exists(), reason=f"no expected output: run `make golden-update` ({EXPECTED})"
    ),
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH"),
]


def test_golden_clip_output_unchanged() -> None:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(run()))  # same float/tuple handling as the stored file
    assert actual == expected, "vision output changed; if intended, run `make golden-update`"
