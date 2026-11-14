"""AGT-05, AGT-06, AGT-08, AGT-09: the coaching agent with a mocked Anthropic client."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from app.coaching import agent, grounding
from app.coaching.schema import SUBMIT_TOOL_NAME, CoachingReport, DrillOption
from app.config import settings
from app.services import coaching

VISION: dict[str, Any] = {
    "metrics": {
        "total_strikes": 2,
        "avg_velocity": 7.25,
        "guard_score": 62.5,
        "strikes_per_minute": 24.0,
        "error_counts": {"dropped_guard": 1, "chicken_wing": 0},
    },
    "strike_events": [
        {
            "timestamp_ms": 1000,
            "frame_number": 30,
            "strike_type": "jab",
            "hand": "left",
            "velocity": 7.0,
            "keypoints": {"nose": [1, 2, 0.9]},
        },
        {"timestamp_ms": 2500, "strike_type": "cross", "hand": "right", "abstained": True},
    ],
    "error_flags": [{"timestamp_ms": 1040, "error_type": "dropped_guard", "severity": "high"}],
    "video_metadata": {"fps": 30.0},
}
PROFILE = {"stance": "orthodox", "experience_level": "beginner"}
DRILLS = [
    DrillOption(id="d-guard", name="Wall Touch Drill", error_type="dropped_guard"),
    DrillOption(id="d-wing", name="Towel Under Arm Drill", error_type="chicken_wing"),
]
GUARD_NOTE = {"text": "Guard dropped on the jab.", "t_ms": 1040, "evidence_field": "error_flags.0"}


def submission(**changes: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "summary": "Sharp jab, but the rear hand drifts.",
        "key_metric": {
            "name": "Guard score",
            "value": 62.5,
            "unit": "%",
            "source_field": "metrics.guard_score",
        },
        "one_thing": "Glue the rear hand to your chin when the jab goes out.",
        "one_thing_evidence": ["error_flags.0"],
        "prescribed_drill": {
            "error_type": "dropped_guard",
            "drill_id": "d-guard",
            "reasoning": "It rebuilds the return to guard.",
        },
        "notes": [GUARD_NOTE],
    }
    report.update(changes)
    return report


def reply(
    tool_input: dict[str, Any] | None,
    input_tokens: int = 10_000,
    output_tokens: int = 1_000,
    stop_reason: str = "tool_use",
) -> SimpleNamespace:
    """A Messages response: a tool call with ``tool_input``, or plain text when None."""
    content: list[SimpleNamespace] = [SimpleNamespace(type="thinking", thinking="")]
    if tool_input is None:
        content.append(SimpleNamespace(type="text", text="Here is my report."))
    else:
        content.append(
            SimpleNamespace(type="tool_use", id="tu_1", name=SUBMIT_TOOL_NAME, input=tool_input)
        )
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture(autouse=True)
def config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_MODEL", "test-model")
    monkeypatch.setattr(settings, "ANTHROPIC_PRICE_INPUT_PER_MTOK", 4.0)
    monkeypatch.setattr(settings, "ANTHROPIC_PRICE_OUTPUT_PER_MTOK", 20.0)
    monkeypatch.setattr(settings, "PROMPT_VERSION", "v1")


def run(client: MagicMock) -> CoachingReport:
    return agent.generate_report(client, VISION, PROFILE, DRILLS, session_id="s1")


def client_returning(*replies: Any) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = list(replies)
    return client


def sent(client: MagicMock, call: int = 0) -> dict[str, Any]:
    kwargs: dict[str, Any] = client.messages.create.call_args_list[call].kwargs
    return kwargs


def request_text(client: MagicMock, call: int = 0) -> str:
    text: str = sent(client, call)["messages"][0]["content"]
    return text


def test_valid_first_try() -> None:
    client = client_returning(reply(submission()))

    report = run(client)

    assert client.messages.create.call_count == 1
    assert report.summary == "Sharp jab, but the rear hand drifts."
    assert report.prescribed_drill.drill_id == "d-guard"
    assert (report.model, report.prompt_version, report.note) == ("test-model", "v1", None)
    assert report.removed_claims == []
    assert report.usage == {
        "input_tokens": 10_000,
        "output_tokens": 1_000,
        "cost_usd": pytest.approx(0.06),
    }
    assert grounding.violations(report, VISION) == []


def test_request_offers_one_unforced_tool_generated_from_the_model() -> None:
    client = client_returning(reply(submission()))
    run(client)

    kwargs = sent(client)
    assert kwargs["model"] == "test-model"
    assert kwargs["system"] == agent.load_prompt("v1")
    # Current models reject a forced tool call; the prompt asks for it instead.
    assert kwargs["tool_choice"] == {"type": "auto"}
    (tool,) = kwargs["tools"]
    assert tool["name"] == SUBMIT_TOOL_NAME
    fields = set(tool["input_schema"]["properties"])
    assert {"summary", "key_metric", "one_thing", "prescribed_drill", "notes"} <= fields
    assert not {"tool_calls", "removed_claims", "prompt_version", "model", "usage"} & fields


def test_request_lists_drills_and_labels_low_confidence_items() -> None:
    client = client_returning(reply(submission()))
    run(client)

    request = request_text(client)
    assert '"id": "d-guard"' in request and '"id": "d-wing"' in request
    assert '"experience_level": "beginner"' in request
    assert "keypoints" not in request

    shown = agent.vision_for_model(VISION, 0.5)
    assert [s["index"] for s in shown["strike_events"]] == [0, 1]
    assert "confidence" not in shown["strike_events"][0]
    assert shown["strike_events"][1]["confidence"] == "low"
    assert "abstained" not in shown["strike_events"][1]


def test_prompt_has_the_low_confidence_rule() -> None:
    prompt = agent.load_prompt("v1")
    assert '"confidence": "low"' in prompt
    assert "Never base `one_thing` or `prescribed_drill` only on low-confidence items" in prompt
    assert SUBMIT_TOOL_NAME in prompt


def test_invalid_then_valid_retries_with_the_errors() -> None:
    bad = submission()
    bad["prescribed_drill"]["drill_id"] = "made-up-drill"
    del bad["summary"]
    client = client_returning(reply(bad, 10_000, 1_000), reply(submission(), 11_000, 500))

    report = run(client)

    assert client.messages.create.call_count == 2
    retry = request_text(client, 1)
    assert retry.startswith(request_text(client, 0))
    assert "previous attempt was rejected" in retry
    assert "summary: Field required" in retry
    assert "unknown drill_id 'made-up-drill'" in retry
    assert report.model == "test-model"
    # Both calls are billed.
    assert report.usage["input_tokens"] == 21_000
    assert report.usage["output_tokens"] == 1_500
    assert report.usage["cost_usd"] == pytest.approx(0.084 + 0.03)


def test_reply_without_the_tool_call_is_retried() -> None:
    client = client_returning(reply(None), reply(submission()))

    report = run(client)

    assert f"without calling the `{SUBMIT_TOOL_NAME}` tool" in request_text(client, 1)
    assert report.model == "test-model"


def test_invalid_twice_falls_back_and_keeps_the_cost() -> None:
    client = client_returning(reply({"summary": 3}), reply({"summary": 3}))

    report = run(client)

    assert client.messages.create.call_count == 2
    assert report.model == agent.FALLBACK_MODEL
    assert report.note == agent.INVALID_NOTE
    assert report.usage["cost_usd"] == pytest.approx(0.12)
    assert grounding.violations(report, VISION) == []


def test_api_error_falls_back() -> None:
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.test"))
    client = client_returning(error)

    report = run(client)

    assert client.messages.create.call_count == 1
    assert (report.model, report.note) == (agent.FALLBACK_MODEL, agent.API_ERROR_NOTE)
    assert report.usage == {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_refusal_or_truncation_falls_back_without_retrying(stop_reason: str) -> None:
    client = client_returning(reply(None, stop_reason=stop_reason))

    report = run(client)

    assert client.messages.create.call_count == 1
    assert report.model == agent.FALLBACK_MODEL
    assert report.usage["cost_usd"] == pytest.approx(0.06)


def test_ungrounded_claims_are_removed_from_a_model_report() -> None:
    notes = [
        GUARD_NOTE,
        {"text": "Big hook at nine seconds.", "t_ms": 9000, "evidence_field": "strike_events.0"},
    ]
    key_metric = {
        "name": "Guard score",
        "value": 90.0,
        "unit": "%",
        "source_field": "metrics.guard_score",
    }
    client = client_returning(reply(submission(notes=notes, key_metric=key_metric)))

    report = run(client)

    assert [n.text for n in report.notes] == ["Guard dropped on the jab."]
    assert report.key_metric.value == 62.5
    assert len(report.removed_claims) == 2
    assert grounding.violations(report, VISION) == []


def test_no_drills_means_no_call() -> None:
    client = MagicMock()

    report = agent.generate_report(client, VISION, PROFILE, [])

    client.messages.create.assert_not_called()
    assert (report.model, report.note) == (agent.FALLBACK_MODEL, agent.NO_DRILLS_NOTE)
    assert report.prescribed_drill.drill_id == ""


def test_fallback_report_is_grounded_and_prescribes_a_real_drill() -> None:
    report = agent.fallback_report(VISION, DRILLS, "why")

    assert report.summary == (
        "Detected 2 strikes with an average velocity of 7.2 sw/s. Guard score: 62%."
    )
    assert report.key_metric.value == 62.5
    assert report.prescribed_drill.drill_id == "d-guard"
    assert [n.evidence_field for n in report.notes] == [
        "metrics.total_strikes",
        "metrics.strikes_per_minute",
        "metrics.error_counts",
    ]
    assert report.note == "why"
    assert grounding.violations(report, VISION) == []


def test_fallback_report_follows_the_dominant_error_and_survives_empty_data() -> None:
    wing = {"metrics": {"error_counts": {"dropped_guard": 1, "chicken_wing": 3}}}
    assert agent.fallback_report(wing, DRILLS, "n").prescribed_drill.drill_id == "d-wing"

    empty = agent.fallback_report({}, DRILLS, "n")
    assert empty.notes == []
    assert empty.key_metric.value == 100.0


def test_cost_formula_uses_config() -> None:
    assert agent.cost_usd(1_000_000, 0) == pytest.approx(4.0)
    assert agent.cost_usd(0, 1_000_000) == pytest.approx(20.0)
    assert agent.cost_usd(2_000, 500) == pytest.approx(0.008 + 0.01)


DRILL_ROWS = [{"id": "d-guard", "name": "Wall Touch Drill", "error_type": "dropped_guard"}]


def test_service_without_api_key_returns_the_basic_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

    report = coaching.generate_coaching_feedback(VISION, PROFILE, DRILL_ROWS)

    assert report["model"] == agent.FALLBACK_MODEL
    assert report["note"] == agent.NO_KEY_NOTE
    assert report["usage"]["cost_usd"] == 0.0
    assert report == coaching.fallback_report(VISION, agent.NO_KEY_NOTE, DRILL_ROWS)


def test_service_calls_the_model_and_returns_a_plain_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_returning(reply(submission()))
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(coaching.anthropic, "Anthropic", lambda **_kw: client)

    report = coaching.generate_coaching_feedback(VISION, PROFILE, DRILL_ROWS, "s1")

    assert report["prescribed_drill"]["drill_id"] == "d-guard"
    assert report["usage"]["cost_usd"] == pytest.approx(0.06)
    assert CoachingReport.model_validate(report).model == "test-model"
