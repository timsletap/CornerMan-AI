import { describe, expect, it } from "vitest";

import { parseCoachingFeedback } from "@/lib/coaching-report";

const REPORT = {
  summary: "Sharp jab, but the rear hand drifts.",
  key_metric: { name: "Guard score", value: 62.5, unit: "%", source_field: "metrics.guard_score" },
  one_thing: "Glue the rear hand to your chin.",
  one_thing_evidence: ["error_flags.0"],
  prescribed_drill: { error_type: "dropped_guard", drill_id: "d1", reasoning: "Rebuilds the return." },
  notes: [{ text: "Guard dropped on the jab.", t_ms: 1040, evidence_field: "error_flags.0" }],
  trends: [],
  tool_calls: [],
  removed_claims: [],
  prompt_version: "v1",
  model: "fallback",
  usage: { input_tokens: 0, output_tokens: 0, cost_usd: 0 },
  note: "Basic report.",
};

describe("parseCoachingFeedback", () => {
  it("reads a structured report", () => {
    expect(parseCoachingFeedback(JSON.stringify(REPORT))).toEqual({
      summary: "Sharp jab, but the rear hand drifts.",
      oneThing: "Glue the rear hand to your chin.",
      keyMetric: "Guard score: 62.5%",
      drillReasoning: "Rebuilds the return.",
      notes: [{ text: "Guard dropped on the jab.", tMs: 1040 }],
      notice: "Basic report.",
    });
  });

  it("puts a space before units other than percent", () => {
    const report = { ...REPORT, key_metric: { ...REPORT.key_metric, name: "Jab speed", value: 7, unit: "sw/s" } };
    expect(parseCoachingFeedback(JSON.stringify(report))?.keyMetric).toBe("Jab speed: 7 sw/s");
  });

  it("still reads reports saved before the structured format", () => {
    const legacy = {
      summary: "s",
      key_metric: "Guard Score: 80%",
      one_thing: "Hands up.",
      prescribed_drill: { error_type: "dropped_guard", reasoning: "r" },
      detailed_notes: ["one", "two"],
      _note: "Basic report.",
    };
    expect(parseCoachingFeedback(JSON.stringify(legacy))).toEqual({
      summary: "s",
      oneThing: "Hands up.",
      keyMetric: "Guard Score: 80%",
      drillReasoning: "r",
      notes: [
        { text: "one", tMs: null },
        { text: "two", tMs: null },
      ],
      notice: "Basic report.",
    });
  });

  it("returns null for missing, non-JSON, and old error payloads", () => {
    expect(parseCoachingFeedback(null)).toBeNull();
    expect(parseCoachingFeedback("plain text")).toBeNull();
    expect(parseCoachingFeedback(JSON.stringify({ summary: "x", _parse_error: true }))).toBeNull();
    expect(parseCoachingFeedback(JSON.stringify({ summary: "x", _api_error: "boom" }))).toBeNull();
  });
});
