"""Compatibility shim: the vision pipeline lives in ``app.vision`` (VIS-08)."""

from app.vision.pipeline import run_vision_analysis

__all__ = ["run_vision_analysis"]
