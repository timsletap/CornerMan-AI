"use client";

import { formatClock } from "@/lib/format";
import { strikeMeta } from "@/lib/strike-meta";
import type { StrikeEventResponse } from "@/lib/types";

interface Props {
  strikes: StrikeEventResponse[];
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
}

/** Every strike in order. Click a row to jump the video to that punch. */
export function StrikeTimeline({ strikes, currentTimeMs, onSeek }: Props) {
  if (strikes.length === 0) {
    return <p className="text-sm text-mute">No strikes were detected in this clip.</p>;
  }

  const topSpeed = Math.max(...strikes.map((s) => s.velocity ?? 0), 0);

  return (
    <ol className="max-h-96 space-y-px overflow-y-auto pr-1">
      {strikes.map((s, i) => {
        const meta = strikeMeta(s.strike_type);
        const isActive = Math.abs(s.timestamp_ms - currentTimeMs) < 400;
        return (
          <li key={s.id}>
            <button
              onClick={() => onSeek(s.timestamp_ms)}
              className={`grid w-full cursor-pointer grid-cols-[1.75rem_2.75rem_6rem_2.5rem_1fr] items-center gap-2 border-l-2 px-2 py-2 text-left transition-colors
                ${isActive ? "border-chalk bg-white/10" : "border-transparent hover:bg-white/5"}`}
            >
              <span className="font-mono text-xs text-dim">{i + 1}</span>
              <span className="font-mono text-xs text-mute">{formatClock(s.timestamp_ms)}</span>
              <span className="flex items-center gap-2 font-display text-lg font-bold uppercase italic text-chalk">
                <span className="h-3.5 w-1" style={{ backgroundColor: meta.color }} />
                {meta.label}
              </span>
              <span className="font-mono text-[0.6875rem] uppercase text-mute">
                {s.hand === "left" ? "L" : "R"}
              </span>
              {s.velocity !== null && topSpeed > 0 ? (
                <span className="flex items-center gap-2">
                  <span className="h-1 flex-1 bg-line">
                    <span
                      className="block h-full bg-chalk/70"
                      style={{ width: `${(s.velocity / topSpeed) * 100}%` }}
                    />
                  </span>
                  <span className="w-9 text-right font-mono text-xs text-mute">
                    {s.velocity.toFixed(1)}
                  </span>
                </span>
              ) : (
                <span />
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
