import type { CoachingFeedback, CoachingReport, LegacyCoachingFeedback } from "@/lib/types";

/** What the corner-talk panel shows, whichever report version the session was saved with. */
export interface CoachingView {
  summary: string;
  oneThing: string | null;
  keyMetric: string | null;
  drillReasoning: string | null;
  notes: { text: string; tMs: number | null }[];
  /** Why this is a basic report, when the model was not used. */
  notice: string | null;
}

function isReport(feedback: CoachingFeedback): feedback is CoachingReport {
  return typeof feedback.key_metric === "object" && feedback.key_metric !== null;
}

function formatMetric({ name, value, unit }: CoachingReport["key_metric"]): string {
  const joined = unit === "%" ? `${value}%` : `${value} ${unit}`.trim();
  return `${name}: ${joined}`;
}

/** Parse `coach_feedback`. Returns null when it is not a report (old error payloads, plain text). */
export function parseCoachingFeedback(raw: string | null): CoachingView | null {
  if (!raw) return null;
  let parsed: CoachingFeedback & { _parse_error?: boolean; _api_error?: string };
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || parsed._parse_error || parsed._api_error) return null;

  if (isReport(parsed)) {
    return {
      summary: parsed.summary,
      oneThing: parsed.one_thing,
      keyMetric: formatMetric(parsed.key_metric),
      drillReasoning: parsed.prescribed_drill?.reasoning ?? null,
      notes: (parsed.notes ?? []).map((n) => ({ text: n.text, tMs: n.t_ms })),
      notice: parsed.note ?? null,
    };
  }

  const legacy: LegacyCoachingFeedback = parsed;
  return {
    summary: legacy.summary,
    oneThing: legacy.one_thing ?? null,
    keyMetric: legacy.key_metric ?? null,
    drillReasoning: legacy.prescribed_drill?.reasoning ?? null,
    notes: (legacy.detailed_notes ?? []).map((text) => ({ text, tMs: null })),
    notice: legacy._note ?? null,
  };
}
