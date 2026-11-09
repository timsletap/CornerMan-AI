"use client";

import type { ProgressResponse } from "@/lib/types";
import { CheckIcon } from "@/components/ui/icons";

const PIPELINE_STEPS = [
  { key: "initializing", label: "Loading the pose model" },
  { key: "pose_extraction", label: "Tracking your body frame by frame" },
  { key: "strike_detection", label: "Finding every punch" },
  { key: "guard_analysis", label: "Checking your guard" },
  { key: "telegraph_detection", label: "Looking for tells" },
  { key: "rendering", label: "Drawing the overlay video" },
  { key: "persisting", label: "Saving the results" },
  { key: "coaching", label: "Writing your corner advice" },
  { key: "drills", label: "Picking drills" },
];

interface Props {
  progress: ProgressResponse | null;
}

export function AnalysisProgress({ progress }: Props) {
  const pct = progress ? Math.round(progress.progress * 100) : 0;
  const detail = progress?.detail || "Waiting for a free corner. This usually starts in a few seconds.";
  const stepIdx = progress
    ? progress.step === "complete"
      ? PIPELINE_STEPS.length
      : PIPELINE_STEPS.findIndex((s) => s.key === progress.step)
    : -1;

  return (
    <div className="hud-frame border border-line bg-panel/85">
      <div className="p-6 sm:p-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow text-blood">{progress ? "In progress" : "In queue"}</p>
            <h1 className="display mt-1 text-4xl text-chalk sm:text-5xl">
              Breaking down your film
            </h1>
          </div>
          <p className="display text-6xl text-chalk sm:text-7xl" aria-hidden="true">
            {pct}
            <span className="text-3xl text-mute">%</span>
          </p>
        </div>

        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label="Analysis progress"
          className="relative mt-6 h-2 overflow-hidden bg-line"
        >
          <div
            className="h-full bg-gradient-to-r from-blood-deep via-blood to-gold transition-[width] duration-700 ease-out"
            style={{ width: `${pct}%` }}
          />
          <div className="absolute inset-y-0 left-0 w-1/4 animate-scan bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>
        <p className="mt-3 text-sm text-mute" aria-live="polite">
          {detail}
        </p>
      </div>

      <ol className="grid border-t border-line sm:grid-cols-3">
        {PIPELINE_STEPS.map((step, idx) => {
          const state = idx < stepIdx ? "done" : idx === stepIdx ? "active" : "pending";
          return (
            <li
              key={step.key}
              className={`flex items-center gap-3 border-b border-line px-5 py-3.5 sm:border-r sm:[&:nth-child(3n)]:border-r-0
                ${state === "active" ? "bg-blood/10" : ""}`}
            >
              <span
                className={`octagon flex h-7 w-7 shrink-0 items-center justify-center font-mono text-[0.6875rem] font-bold
                  ${state === "done" ? "bg-go text-canvas" : state === "active" ? "animate-pulse bg-blood text-white" : "bg-panel-2 text-dim"}`}
              >
                {state === "done" ? <CheckIcon /> : idx + 1}
              </span>
              <span
                className={`text-sm ${state === "pending" ? "text-dim" : state === "active" ? "font-medium text-chalk" : "text-mute"}`}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>

      <p className="px-6 py-4 text-xs text-dim">
        You can leave this page. The breakdown keeps running and will be in your camp when
        it&apos;s done.
      </p>
    </div>
  );
}
