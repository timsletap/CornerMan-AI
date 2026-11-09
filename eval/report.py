"""Eval report models (FRD section 6.6). Every metric in a report comes from these."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Detection(_Model):
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    precision: float
    recall: float
    f1: float


class ClassScore(_Model):
    precision: float
    recall: float
    f1: float
    support: int = Field(ge=0, description="Matched pairs whose label has this type")


class Confusion(_Model):
    labels: list[str]
    matrix: list[list[int]] = Field(description="matrix[label][prediction] over matched pairs")
    unclassified: list[int] = Field(
        default=[], description="Per label: matched predictions typed outside `labels`"
    )


class StrikeType(_Model):
    macro_f1: float = Field(description="Mean F1 over strike types with support > 0")
    per_class: dict[str, ClassScore]
    confusion: Confusion


class IdentitySwitches(_Model):
    total: int = Field(ge=0)
    per_clip: dict[str, int]


class Throughput(_Model):
    stage1_x_realtime: float | None = Field(
        description="Video seconds per wall-clock second for pose inference; null when "
        "every clip came from the poses cache"
    )
    stages23_x_realtime: float | None
    hardware: str


class Calibration(_Model):
    ece_before: float | None = None
    ece_after: float | None = None


class TagScore(_Model):
    clips: int
    detection_f1: float
    detection_precision: float
    detection_recall: float


class Report(_Model):
    git_sha: str
    split: str
    created_at: datetime
    config_hash: str
    match_window_ms: int
    clips: list[str] = []
    detection: Detection
    strike_type: StrikeType
    errors: dict[str, Detection]
    identity_switches: IdentitySwitches | None
    throughput: Throughput
    calibration: Calibration = Calibration()
    by_tag: dict[str, TagScore] = {}

    def metrics(self) -> dict[str, object]:
        """The deterministic part of the report (no timestamps, timings, or SHA)."""
        return self.model_dump(mode="json", exclude={"git_sha", "created_at", "throughput"})
