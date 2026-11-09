"""Evaluation harness: labels, matching, metrics, and reports (FRD sections 6.5, 6.6).

The harness runs the backend's vision stages, so ``backend`` is put on ``sys.path`` here;
``python -m eval.run`` then works from the repo root without setting PYTHONPATH.
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
