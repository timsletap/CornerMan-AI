"""AGT-05: the report models and the tool schema generated from them."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.coaching.schema import PrescribedDrill, ReportSubmission, submission_schema

DRILL = {"error_type": "dropped_guard", "drill_id": "d1", "reasoning": "r"}


def test_drill_id_must_be_one_of_the_offered_drills() -> None:
    context = {"drill_ids": {"d1", "d2"}}
    assert PrescribedDrill.model_validate(DRILL, context=context).drill_id == "d1"
    with pytest.raises(ValidationError, match="unknown drill_id 'nope'"):
        PrescribedDrill.model_validate({**DRILL, "drill_id": "nope"}, context=context)
    # Without a drill list (a stored report being read back) any id is accepted.
    assert PrescribedDrill.model_validate({**DRILL, "drill_id": "nope"}).drill_id == "nope"


def test_submission_rejects_extra_fields_and_more_than_five_notes() -> None:
    base: dict[str, Any] = {
        "summary": "s",
        "key_metric": {"name": "n", "value": 1, "unit": "%", "source_field": "metrics.x"},
        "one_thing": "o",
        "prescribed_drill": DRILL,
    }
    assert ReportSubmission.model_validate(base).notes == []
    with pytest.raises(ValidationError):
        ReportSubmission.model_validate({**base, "model": "sneaky"})
    notes = [{"text": "t", "t_ms": None, "evidence_field": "metrics.x"}] * 6
    with pytest.raises(ValidationError):
        ReportSubmission.model_validate({**base, "notes": notes})


def test_tool_schema_has_only_the_fields_the_model_writes() -> None:
    schema = submission_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert {"summary", "key_metric", "one_thing", "prescribed_drill"} <= set(schema["required"])
    assert "usage" not in schema["properties"]
