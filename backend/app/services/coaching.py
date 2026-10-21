"""Coaching agent service - Anthropic Claude integration for CornerMan persona.

Implements AGT-01 through AGT-04 from the FRD:
- Context ingestion (vision JSON + user profile)
- Persona prompting (CornerMan: direct, technical, encouraging)
- Drill mapping (deterministic error-to-drill lookup)
- Structured response (summary, key metric, one thing, prescribed drill)
"""

import json
from typing import Any

import anthropic

from app.config import settings
from app.services.drill_mapping import get_drills_for_error

CORNERMAN_SYSTEM_PROMPT = """\
You are CornerMan, an elite-level striking coach for combat sports (MMA, Boxing, Muay Thai). \
You speak directly, technically, and encouragingly -- like the best corner coaches in the sport.

RULES:
- Never say "As an AI" or "As a language model" or any similar disclaimer. You ARE CornerMan.
- Be direct and specific. Reference exact timestamps from the data when possible.
- Use proper striking terminology (jab, cross, hook, uppercut, body shot).
- Be encouraging but honest. Fighters respect truthful feedback.
- Keep it concise. Fighters absorb short, punchy directives.

You will receive:
1. Vision analysis data containing strike events, error flags, and metrics from a training video.
2. The fighter's profile (stance, experience level, weight class).

You MUST respond with EXACTLY this JSON structure (no markdown, no code fences, raw JSON only):
{
    "summary": "<2-3 sentence overview of the session>",
    "key_metric": "<The single most important metric with its value>",
    "one_thing": "<The ONE corrective action for the biggest impact>",
    "prescribed_drill": {
        "error_type": "<dropped_guard|chicken_wing|other>",
        "reasoning": "<Why this drill addresses the issue>"
    },
    "detailed_notes": [
        "<Specific observation 1>",
        "<Specific observation 2>",
        "<Specific observation 3>"
    ]
}"""


def llm_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost in USD of one call, from token counts and the configured per-MTok prices."""
    return (
        input_tokens * settings.ANTHROPIC_PRICE_INPUT_PER_MTOK / 1e6
        + output_tokens * settings.ANTHROPIC_PRICE_OUTPUT_PER_MTOK / 1e6
    )


def generate_coaching_feedback(
    vision_data: dict[str, Any],
    user_profile: dict[str, Any],
) -> dict[str, Any]:
    """Generate coaching feedback from vision analysis data. Called from Celery (sync)."""
    if not settings.ANTHROPIC_API_KEY:
        metrics = vision_data.get("metrics", {})
        return {
            "summary": (
                f"Detected {metrics.get('total_strikes', 0)} strikes with an average velocity of "
                f"{metrics.get('avg_velocity', 0):.1f} u/s. Guard score: {metrics.get('guard_score', 100):.0f}%."
            ),
            "key_metric": f"Guard Score: {metrics.get('guard_score', 100):.0f}%",
            "one_thing": "Focus on keeping your guard hand tight to your chin when throwing combinations.",
            "prescribed_drill": {
                "error_type": "dropped_guard",
                "reasoning": "Guard maintenance is fundamental.",
            },
            "detailed_notes": [
                f"Total strikes detected: {metrics.get('total_strikes', 0)}",
                f"Strikes per minute: {metrics.get('strikes_per_minute', 0):.1f}",
                f"Errors found: {sum(metrics.get('error_counts', {}).values())}",
            ],
            "mapped_drills": [],
            "_usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            "_note": "AI coaching unavailable — set ANTHROPIC_API_KEY for full analysis",
        }

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # AGT-01: Build context payload
    user_context = (
        f"Fighter Profile:\n"
        f"- Stance: {user_profile.get('stance', 'unknown')}\n"
        f"- Experience: {user_profile.get('experience_level', 'unknown')}\n"
        f"- Weight Class: {user_profile.get('weight_class', 'unknown')}\n"
    )

    trimmed_vision = {
        "metrics": vision_data.get("metrics", {}),
        "strike_events": vision_data.get("strike_events", [])[:50],
        "error_flags": vision_data.get("error_flags", []),
        "video_metadata": vision_data.get("video_metadata", {}),
        "occluded_ranges": vision_data.get("occluded_ranges", []),
    }

    user_message = (
        f"{user_context}\n\nVision Analysis Data:\n{json.dumps(trimmed_vision, indent=2)}"
    )

    # AGT-02: Call Claude with persona prompt
    raw_response = ""
    usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    try:
        message = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            system=CORNERMAN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        # Record cost before parsing: a response we can't parse is still billed.
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "cost_usd": llm_cost_usd(message.usage.input_tokens, message.usage.output_tokens),
        }

        raw_response = message.content[0].text

        # AGT-04: Parse structured response
        coaching_response = json.loads(raw_response)

        # AGT-03: Deterministic drill mapping overlay
        prescribed_error_type = coaching_response.get("prescribed_drill", {}).get(
            "error_type", "other"
        )
        drill_names = get_drills_for_error(prescribed_error_type)
        coaching_response["mapped_drills"] = drill_names
        coaching_response["_usage"] = usage

        return coaching_response

    except json.JSONDecodeError:
        return {
            "summary": raw_response[:500] if raw_response else "Unable to parse coaching response.",
            "key_metric": None,
            "one_thing": None,
            "prescribed_drill": None,
            "mapped_drills": [],
            "detailed_notes": [],
            "_usage": usage,
            "_parse_error": True,
        }
    except anthropic.APIError as e:
        return {
            "summary": f"Coaching analysis unavailable: {e}",
            "key_metric": None,
            "one_thing": None,
            "prescribed_drill": None,
            "mapped_drills": [],
            "detailed_notes": [],
            "_api_error": str(e),
        }
