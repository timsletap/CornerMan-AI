"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { errorMeta } from "@/lib/strike-meta";
import type { ErrorFlagResponse } from "@/lib/types";
import { Badge, type BadgeColor } from "@/components/ui/badge";

interface Props {
  errors: ErrorFlagResponse[];
  sessionId: string;
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
}

const severityColors: Record<string, BadgeColor> = {
  high: "red",
  medium: "yellow",
  low: "zinc",
};

/** Flagged mistakes. Click one to watch it; dispute it if the call is wrong. */
export function ErrorFlagList({ errors, sessionId, currentTimeMs, onSeek }: Props) {
  const [disputed, setDisputed] = useState<Set<string>>(
    new Set(errors.filter((e) => e.user_disputed).map((e) => e.id)),
  );
  const [failed, setFailed] = useState<string | null>(null);

  async function handleDispute(errorId: string) {
    setFailed(null);
    try {
      await api.disputeError(sessionId, errorId);
      setDisputed((prev) => new Set([...prev, errorId]));
    } catch {
      setFailed(errorId);
    }
  }

  if (errors.length === 0) {
    return (
      <p className="text-sm text-go">Clean round. Nothing was flagged in this clip.</p>
    );
  }

  return (
    <ul className="max-h-72 space-y-px overflow-y-auto pr-1">
      {errors.map((e) => {
        const meta = errorMeta(e.error_type);
        const isActive = Math.abs(e.timestamp_ms - currentTimeMs) < 400;
        const isDisputed = disputed.has(e.id);
        return (
          <li
            key={e.id}
            className={`flex items-center gap-3 border-l-2 px-2 py-2.5 transition-colors
              ${isActive ? "border-blood bg-blood/10" : "border-transparent hover:bg-white/5"}
              ${isDisputed ? "opacity-50" : ""}`}
          >
            <button
              onClick={() => onSeek(e.timestamp_ms)}
              className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
            >
              <span className="w-10 shrink-0 font-mono text-xs text-mute">
                {formatClock(e.timestamp_ms)}
              </span>
              <span className="min-w-0">
                <span className="block font-display text-lg font-bold uppercase italic leading-tight text-chalk">
                  {meta.label}
                </span>
                <span className="block truncate text-xs text-mute">{meta.blurb}</span>
              </span>
            </button>
            <Badge color={severityColors[e.severity] ?? "zinc"}>{e.severity}</Badge>
            <button
              disabled={isDisputed}
              onClick={() => handleDispute(e.id)}
              className="shrink-0 cursor-pointer text-xs text-mute underline underline-offset-4 hover:text-chalk disabled:cursor-default disabled:no-underline"
            >
              {isDisputed ? "Disputed" : failed === e.id ? "Retry" : "Dispute"}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
