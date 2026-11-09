import type { AnalysisSessionResponse, StrikeEventResponse, StrikeType } from "./types";

export interface TypeCount {
  type: StrikeType;
  count: number;
  /** Fraction of all strikes, 0 to 1. */
  share: number;
}

export interface StrikeSummary {
  total: number;
  /** Most thrown first; types with no strikes are left out. */
  byType: TypeCount[];
  byHand: { left: number; right: number };
  /** The strike with the highest velocity, if any strike has one. */
  fastest: StrikeEventResponse | null;
}

export function summarizeStrikes(strikes: StrikeEventResponse[]): StrikeSummary {
  const counts = new Map<StrikeType, number>();
  const byHand = { left: 0, right: 0 };
  let fastest: StrikeEventResponse | null = null;

  for (const strike of strikes) {
    counts.set(strike.strike_type, (counts.get(strike.strike_type) ?? 0) + 1);
    byHand[strike.hand] += 1;
    if (strike.velocity !== null && (fastest?.velocity ?? -Infinity) < strike.velocity) {
      fastest = strike;
    }
  }

  const total = strikes.length;
  const byType = [...counts.entries()]
    .map(([type, count]) => ({ type, count, share: count / total }))
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));

  return { total, byType, byHand, fastest };
}

export type GuardTone = "good" | "warn" | "bad" | "none";

/** Guard score (0 to 100, share of strikes thrown with the guard up) as a verdict. */
export function guardGrade(score: number | null | undefined): { tone: GuardTone; label: string } {
  if (score === null || score === undefined) return { tone: "none", label: "No read" };
  if (score >= 80) return { tone: "good", label: "Tight" };
  if (score >= 50) return { tone: "warn", label: "Leaky" };
  return { tone: "bad", label: "Open" };
}

export interface CareerStats {
  /** Completed analyses. */
  sessions: number;
  totalStrikes: number;
  avgGuard: number | null;
  bestGuard: number | null;
  /** Guard scores of completed analyses, oldest first. */
  guardTrend: number[];
}

export function careerStats(sessions: AnalysisSessionResponse[]): CareerStats {
  const completed = sessions
    .filter((s) => s.status === "completed")
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const guardTrend = completed
    .map((s) => s.guard_score)
    .filter((g): g is number => g !== null);

  return {
    sessions: completed.length,
    totalStrikes: completed.reduce((sum, s) => sum + (s.total_strikes ?? 0), 0),
    avgGuard: guardTrend.length
      ? guardTrend.reduce((sum, g) => sum + g, 0) / guardTrend.length
      : null,
    bestGuard: guardTrend.length ? Math.max(...guardTrend) : null,
    guardTrend,
  };
}

/** Where a moment sits on a timeline, as a percentage (0 to 100) of the clip length. */
export function timelinePercent(tMs: number, durationMs: number): number {
  if (durationMs <= 0) return 0;
  return Math.min(100, Math.max(0, (tMs / durationMs) * 100));
}

/** Clip length in ms: from the video metadata when known, else the last event plus a beat. */
export function clipDurationMs(
  durationSeconds: number | null | undefined,
  eventTimesMs: number[],
): number {
  if (durationSeconds && durationSeconds > 0) return durationSeconds * 1000;
  return eventTimesMs.length ? Math.max(...eventTimesMs) + 1000 : 0;
}
