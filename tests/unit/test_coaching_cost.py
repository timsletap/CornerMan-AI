"""AGT-09: LLM cost comes from configured per-MTok prices and actual token usage."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.services import coaching

VISION = {"metrics": {"total_strikes": 3}, "strike_events": [], "error_flags": []}
PROFILE = {"stance": "orthodox"}


def fake_message(text: str, input_tokens: int, output_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ANTHROPIC_PRICE_INPUT_PER_MTOK", 4.0)
    monkeypatch.setattr(settings, "ANTHROPIC_PRICE_OUTPUT_PER_MTOK", 20.0)
    mock = MagicMock()
    monkeypatch.setattr(coaching.anthropic, "Anthropic", lambda **_kw: mock)
    return mock


def test_cost_formula_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_PRICE_INPUT_PER_MTOK", 4.0)
    monkeypatch.setattr(settings, "ANTHROPIC_PRICE_OUTPUT_PER_MTOK", 20.0)
    assert coaching.llm_cost_usd(1_000_000, 0) == pytest.approx(4.0)
    assert coaching.llm_cost_usd(0, 1_000_000) == pytest.approx(20.0)
    assert coaching.llm_cost_usd(2_000, 500) == pytest.approx(0.008 + 0.01)


def test_successful_call_reports_cost(client: MagicMock) -> None:
    body = '{"summary": "s", "prescribed_drill": {"error_type": "other"}}'
    client.messages.create.return_value = fake_message(body, 10_000, 1_000)

    usage: dict[str, Any] = coaching.generate_coaching_feedback(VISION, PROFILE)["_usage"]

    assert usage == {
        "input_tokens": 10_000,
        "output_tokens": 1_000,
        "cost_usd": pytest.approx(0.06),
    }
    assert client.messages.create.call_args.kwargs["model"] == settings.ANTHROPIC_MODEL


def test_unparseable_response_still_reports_cost(client: MagicMock) -> None:
    client.messages.create.return_value = fake_message("not json", 10_000, 1_000)

    result = coaching.generate_coaching_feedback(VISION, PROFILE)

    assert result["_parse_error"] is True
    assert result["_usage"]["cost_usd"] == pytest.approx(0.06)


def test_fallback_without_api_key_costs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert coaching.generate_coaching_feedback(VISION, PROFILE)["_usage"]["cost_usd"] == 0.0
