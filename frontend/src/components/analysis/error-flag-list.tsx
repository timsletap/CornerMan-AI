"use client";

import { useState } from "react";
import type { ErrorFlagResponse } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

interface Props {
  errors: ErrorFlagResponse[];
  sessionId: string;
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
}

const severityColors: Record<string, "red" | "yellow" | "zinc"> = {
  high: "red",
  medium: "yellow",
  low: "zinc",
};

function formatTime(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
}

export function ErrorFlagList({ errors, sessionId, currentTimeMs, onSeek }: Props) {
  const [disputed, setDisputed] = useState<Set<string>>(
    new Set(errors.filter((e) => e.user_disputed).map((e) => e.id)),
  );

  async function handleDispute(errorId: string) {
    try {
      await api.disputeError(sessionId, errorId);
      setDisputed((prev) => new Set([...prev, errorId]));
    } catch {
      // ignore
    }
  }

  if (errors.length === 0) {
    return <p className="text-sm text-zinc-500">No errors flagged</p>;
  }

  return (
    <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
      {errors.map((e) => {
        const isActive = Math.abs(e.timestamp_ms - currentTimeMs) < 500;
        const isDisputed = disputed.has(e.id);
        return (
          <div
            key={e.id}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors
              ${isActive ? "bg-red-900/30 border border-red-800" : "hover:bg-zinc-800/50"}`}
            onClick={() => onSeek(e.timestamp_ms)}
          >
            <span className="text-xs text-zinc-500 font-mono w-10 flex-shrink-0">
              {formatTime(e.timestamp_ms)}
            </span>
            <Badge color={severityColors[e.severity] || "zinc"}>
              {e.severity}
            </Badge>
            <span className="text-sm text-zinc-300 flex-1">
              {e.error_type.replace("_", " ")}
            </span>
            <Button
              variant={isDisputed ? "ghost" : "outline"}
              size="sm"
              disabled={isDisputed}
              onClick={(ev) => { ev.stopPropagation(); handleDispute(e.id); }}
            >
              {isDisputed ? "Disputed" : "Dispute"}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
