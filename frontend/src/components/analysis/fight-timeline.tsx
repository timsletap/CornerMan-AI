"use client";

import type { MouseEvent } from "react";
import { timelinePercent } from "@/lib/fight-stats";
import { formatClock } from "@/lib/format";
import { errorMeta, strikeMeta } from "@/lib/strike-meta";
import type { ErrorFlagResponse, Hand, StrikeEventResponse } from "@/lib/types";

interface Props {
  strikes: StrikeEventResponse[];
  errors: ErrorFlagResponse[];
  /** Clip length in ms. */
  durationMs: number;
  /** Current playback position in ms. */
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
}

/** How many earlier flags share this flag's timestamp. */
function sameMomentBefore(flags: ErrorFlagResponse[], index: number): number {
  return flags.slice(0, index).filter((f) => f.timestamp_ms === flags[index].timestamp_ms).length;
}

const HAND_LANES: { hand: Hand; label: string }[] = [
  { hand: "left", label: "Left" },
  { hand: "right", label: "Right" },
];

/**
 * The whole clip as a scrubbable strip: one lane per hand with a marker for each strike,
 * a lane of flagged mistakes, and a playhead that follows the video. Click anywhere to
 * jump there.
 */
export function FightTimeline({ strikes, errors, durationMs, currentTimeMs, onSeek }: Props) {
  if (durationMs <= 0) return null;

  const seekFromClick = (e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    onSeek(fraction * durationMs);
  };
  const usedTypes = [...new Set(strikes.map((s) => s.strike_type))];

  return (
    <div>
      <div className="flex">
        {/* Lane labels */}
        <div className="flex w-12 shrink-0 flex-col font-mono text-[0.625rem] uppercase tracking-wider text-dim">
          <span className="flex h-6 items-center">Flags</span>
          {HAND_LANES.map((lane) => (
            <span key={lane.hand} className="flex h-9 items-center">
              {lane.label}
            </span>
          ))}
        </div>

        {/* Track */}
        <div className="relative min-w-0 flex-1 cursor-crosshair" onClick={seekFromClick}>
          {/* Flags lane */}
          <div className="relative h-6">
            {errors.map((flag, i) => (
              <button
                key={flag.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onSeek(flag.timestamp_ms);
                }}
                title={`${errorMeta(flag.error_type).label} at ${formatClock(flag.timestamp_ms)}`}
                aria-label={`${errorMeta(flag.error_type).label} at ${formatClock(flag.timestamp_ms)}`}
                className={`absolute top-1 h-3.5 w-3.5 -translate-x-1/2 rotate-45 cursor-pointer border border-canvas transition-transform hover:scale-125
                  ${flag.user_disputed ? "bg-dim" : flag.error_type === "dropped_guard" ? "bg-blood" : "bg-gold"}`}
                style={{
                  left: `${timelinePercent(flag.timestamp_ms, durationMs)}%`,
                  // Flags on the same punch sit side by side instead of hiding each other
                  marginLeft: sameMomentBefore(errors, i) * 12,
                }}
              />
            ))}
          </div>

          {/* Hand lanes */}
          {HAND_LANES.map((lane) => (
            <div key={lane.hand} className="relative h-9 border-t border-line bg-panel-2/60">
              {strikes
                .filter((s) => s.hand === lane.hand)
                .map((s) => {
                  const meta = strikeMeta(s.strike_type);
                  const label = `${meta.label}, ${s.hand} hand, at ${formatClock(s.timestamp_ms)}`;
                  return (
                    <button
                      key={s.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSeek(s.timestamp_ms);
                      }}
                      title={label}
                      aria-label={label}
                      className="absolute inset-y-1.5 w-1.5 -translate-x-1/2 cursor-pointer rounded-[1px] transition-transform hover:scale-x-[2] hover:scale-y-125"
                      style={{
                        left: `${timelinePercent(s.timestamp_ms, durationMs)}%`,
                        backgroundColor: meta.color,
                      }}
                    />
                  );
                })}
            </div>
          ))}

          {/* Playhead */}
          <div
            className="pointer-events-none absolute inset-y-0 w-px bg-chalk"
            style={{ left: `${timelinePercent(currentTimeMs, durationMs)}%` }}
          >
            <span className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-chalk" />
          </div>
        </div>
      </div>

      {/* Time ruler */}
      <div className="ml-12 mt-1.5 flex justify-between font-mono text-[0.625rem] text-dim">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <span key={f}>{formatClock(durationMs * f)}</span>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-mute">
        {usedTypes.map((type) => (
          <span key={type} className="flex items-center gap-1.5">
            <span className="h-2.5 w-1.5 rounded-[1px]" style={{ backgroundColor: strikeMeta(type).color }} />
            {strikeMeta(type).label}
          </span>
        ))}
        {errors.length > 0 && (
          <>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rotate-45 bg-blood" /> Dropped guard
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rotate-45 bg-gold" /> Telegraph
            </span>
          </>
        )}
      </div>
    </div>
  );
}
