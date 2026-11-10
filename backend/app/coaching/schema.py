"""Coaching report models (FRD section 6.7).

``ReportSubmission`` is what the model fills in through the ``submit_coaching_report``
tool. ``CoachingReport`` adds the fields the server fills in (audit trail, versions,
usage) and is what gets stored.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

ErrorKind = Literal["dropped_guard", "chicken_wing", "other"]

SUBMIT_TOOL_NAME = "submit_coaching_report"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DrillOption(_Model):
    """A drill the report may prescribe (a row of the drills table)."""

    id: str
    name: str
    error_type: str
    description: str = ""


class KeyMetric(_Model):
    name: str
    value: float
    unit: str
    source_field: str = Field(
        description='Dotted path into the vision data, e.g. "metrics.guard_score"'
    )


class PrescribedDrill(_Model):
    error_type: ErrorKind
    drill_id: str = Field(description="Id of one of the drills offered in the request")
    reasoning: str

    @field_validator("drill_id")
    @classmethod
    def _drill_exists(cls, value: str, info: ValidationInfo) -> str:
        allowed = (info.context or {}).get("drill_ids")
        if allowed is not None and value not in allowed:
            raise ValueError(f"unknown drill_id {value!r}; choose one of {sorted(allowed)}")
        return value


class Note(_Model):
    text: str
    t_ms: int | None = Field(description="Time the note refers to, ms from video start, or null")
    evidence_field: str = Field(
        description='Dotted path into the vision data, e.g. "strike_events.3", '
        'or "tool:<call_id>.<path>" for a tool result'
    )


class Trend(_Model):
    metric: str
    direction: Literal["improving", "worsening", "flat"]
    summary: str
    evidence_tool_call_id: str


class ToolCallRecord(_Model):
    id: str
    name: str
    arguments: dict[str, Any]
    result_digest: str = Field(description="Short hash of the result, for audit")


class ReportSubmission(_Model):
    """The part of the report the model writes."""

    summary: str = Field(description="2-3 sentence overview of the session")
    key_metric: KeyMetric
    one_thing: str = Field(description="The one corrective action with the biggest impact")
    one_thing_evidence: list[str] = Field(
        default=[],
        description="Dotted paths into the vision data that one_thing is based on",
    )
    prescribed_drill: PrescribedDrill
    notes: list[Note] = Field(default=[], max_length=5)
    trends: list[Trend] = []


class CoachingReport(ReportSubmission):
    tool_calls: list[ToolCallRecord] = []
    removed_claims: list[str] = Field(
        default=[], description="Claims dropped by the grounding check, with the reason"
    )
    prompt_version: str
    model: str
    usage: dict[str, int | float] = Field(
        description="input_tokens, output_tokens, cost_usd over every call for this report"
    )
    note: str | None = Field(
        default=None, description="Why this is a basic report, when the model was not used"
    )


def submission_schema() -> dict[str, Any]:
    """JSON Schema for the ``submit_coaching_report`` tool input."""
    return ReportSubmission.model_json_schema()
