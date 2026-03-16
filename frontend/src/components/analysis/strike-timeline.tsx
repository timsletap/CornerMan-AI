"use client";

import type { StrikeEventResponse } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

interface Props {
  strikes: StrikeEventResponse[];
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
}

function formatTime(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

const typeColors: Record<string, "red" | "blue" | "yellow" | "green" | "orange" | "zinc"> = {
  jab: "blue",
  cross: "red",
  hook: "orange",
  uppercut: "yellow",
  body_shot: "green",
  elbow: "red",
  knee: "red",
  kick: "orange",
  other: "zinc",
};

export function StrikeTimeline({ strikes, currentTimeMs, onSeek }: Props) {
  if (strikes.length === 0) {
    return <p className="text-sm text-zinc-500">No strikes detected</p>;
  }

  return (
    <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
      {strikes.map((s) => {
        const isActive = Math.abs(s.timestamp_ms - currentTimeMs) < 500;
        return (
          <button
            key={s.id}
            onClick={() => onSeek(s.timestamp_ms)}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors
              ${isActive ? "bg-red-900/30 border border-red-800" : "hover:bg-zinc-800/50"}`}
          >
            <span className="text-xs text-zinc-500 font-mono w-10 flex-shrink-0">
              {formatTime(s.timestamp_ms)}
            </span>
            <Badge color={typeColors[s.strike_type] || "zinc"}>
              {s.strike_type.replace("_", " ")}
            </Badge>
            <span className="text-xs text-zinc-400 capitalize">{s.hand}</span>
            {s.velocity && (
              <span className="text-xs text-zinc-500 ml-auto">
                {s.velocity.toFixed(1)} u/s
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
