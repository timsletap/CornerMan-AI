import { describe, expect, it } from "vitest";

import {
  careerStats,
  clipDurationMs,
  guardGrade,
  summarizeStrikes,
  timelinePercent,
} from "../fight-stats";
import { formatBytes, formatClock, formatDuration, humanize } from "../format";
import type { AnalysisSessionResponse, StrikeEventResponse } from "../types";

function strike(overrides: Partial<StrikeEventResponse>): StrikeEventResponse {
  return {
    id: Math.random().toString(36),
    timestamp_ms: 0,
    frame_number: 0,
    strike_type: "jab",
    hand: "left",
    velocity: 1,
    keypoints: null,
    ...overrides,
  };
}

function session(overrides: Partial<AnalysisSessionResponse>): AnalysisSessionResponse {
  return {
    id: "s",
    user_id: "u",
    video_id: "v",
    status: "completed",
    total_strikes: 0,
    avg_velocity: null,
    guard_score: null,
    coach_feedback: null,
    annotated_video_path: null,
    processing_started_at: null,
    processing_completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("summarizeStrikes", () => {
  it("counts by type and hand and finds the fastest strike", () => {
    const summary = summarizeStrikes([
      strike({ strike_type: "jab", hand: "left", velocity: 3 }),
      strike({ strike_type: "jab", hand: "left", velocity: 5 }),
      strike({ strike_type: "cross", hand: "right", velocity: 9 }),
      strike({ strike_type: "hook", hand: "left", velocity: null }),
    ]);

    expect(summary.total).toBe(4);
    expect(summary.byType.map((t) => [t.type, t.count])).toEqual([
      ["jab", 2],
      ["cross", 1],
      ["hook", 1],
    ]);
    expect(summary.byType[0].share).toBe(0.5);
    expect(summary.byHand).toEqual({ left: 3, right: 1 });
    expect(summary.fastest?.velocity).toBe(9);
  });

  it("handles a clip with no strikes", () => {
    expect(summarizeStrikes([])).toEqual({
      total: 0,
      byType: [],
      byHand: { left: 0, right: 0 },
      fastest: null,
    });
  });
});

describe("guardGrade", () => {
  it("grades at the 80 and 50 boundaries", () => {
    expect(guardGrade(80).tone).toBe("good");
    expect(guardGrade(79.9).tone).toBe("warn");
    expect(guardGrade(50).tone).toBe("warn");
    expect(guardGrade(49.9).tone).toBe("bad");
    expect(guardGrade(0).tone).toBe("bad");
    expect(guardGrade(null).tone).toBe("none");
  });
});

describe("careerStats", () => {
  it("uses only completed sessions, oldest first", () => {
    const stats = careerStats([
      session({ created_at: "2026-03-01T00:00:00Z", total_strikes: 10, guard_score: 90 }),
      session({ created_at: "2026-01-01T00:00:00Z", total_strikes: 20, guard_score: 60 }),
      session({ status: "failed", total_strikes: 99, guard_score: 1 }),
      session({ created_at: "2026-02-01T00:00:00Z", total_strikes: null, guard_score: null }),
    ]);

    expect(stats.sessions).toBe(3);
    expect(stats.totalStrikes).toBe(30);
    expect(stats.guardTrend).toEqual([60, 90]);
    expect(stats.avgGuard).toBe(75);
    expect(stats.bestGuard).toBe(90);
  });

  it("has no guard numbers before the first completed analysis", () => {
    const stats = careerStats([session({ status: "processing" })]);
    expect(stats).toEqual({
      sessions: 0,
      totalStrikes: 0,
      avgGuard: null,
      bestGuard: null,
      guardTrend: [],
    });
  });
});

describe("timeline helpers", () => {
  it("places a moment as a clamped percentage of the clip", () => {
    expect(timelinePercent(2500, 10_000)).toBe(25);
    expect(timelinePercent(-5, 10_000)).toBe(0);
    expect(timelinePercent(20_000, 10_000)).toBe(100);
    expect(timelinePercent(100, 0)).toBe(0);
  });

  it("prefers the video's duration and falls back to the last event", () => {
    expect(clipDurationMs(12.5, [900])).toBe(12_500);
    expect(clipDurationMs(null, [900, 4200])).toBe(5200);
    expect(clipDurationMs(undefined, [])).toBe(0);
  });
});

describe("format", () => {
  it("formats clock times, durations, sizes, and enum values", () => {
    expect(formatClock(83_400)).toBe("1:23");
    expect(formatClock(0)).toBe("0:00");
    expect(formatDuration(8.24)).toBe("8.2s");
    expect(formatDuration(65)).toBe("1m 05s");
    expect(formatDuration(null)).toBe("--");
    expect(formatBytes(512 * 1024)).toBe("512 KB");
    expect(formatBytes(5.5 * 1024 * 1024)).toBe("5.5 MB");
    expect(humanize("light_heavyweight")).toBe("Light heavyweight");
  });
});
