"use client";

import type { ProgressResponse } from "@/lib/types";
import { Card } from "@/components/ui/card";

const PIPELINE_STEPS = [
  { key: "initializing", label: "Loading Model", icon: "01" },
  { key: "pose_extraction", label: "Tracking Poses", icon: "02" },
  { key: "strike_detection", label: "Detecting Strikes", icon: "03" },
  { key: "guard_analysis", label: "Guard Analysis", icon: "04" },
  { key: "telegraph_detection", label: "Telegraph Detection", icon: "05" },
  { key: "rendering", label: "Rendering Overlay", icon: "06" },
  { key: "persisting", label: "Saving Results", icon: "07" },
  { key: "coaching", label: "AI Coaching", icon: "08" },
  { key: "drills", label: "Mapping Drills", icon: "09" },
  { key: "complete", label: "Complete", icon: "10" },
];

interface Props {
  progress: ProgressResponse | null;
}

export function AnalysisProgress({ progress }: Props) {
  const currentStep = progress?.step || "queued";
  const pct = progress ? Math.round(progress.progress * 100) : 0;
  const detail = progress?.detail || "Waiting in queue...";

  const currentStepIdx = PIPELINE_STEPS.findIndex((s) => s.key === currentStep);

  return (
    <Card className="space-y-6">
      {/* Main progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-zinc-300">{detail}</span>
          <span className="text-sm font-mono text-zinc-500">{pct}%</span>
        </div>
        <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{
              width: `${pct}%`,
              background:
                "linear-gradient(90deg, #ef4444 0%, #f97316 40%, #eab308 70%, #22c55e 100%)",
            }}
          />
        </div>
      </div>

      {/* Pipeline step indicators */}
      <div className="grid grid-cols-5 gap-2">
        {PIPELINE_STEPS.map((step, idx) => {
          let state: "done" | "active" | "pending" = "pending";
          if (idx < currentStepIdx) state = "done";
          else if (idx === currentStepIdx) state = "active";

          return (
            <div
              key={step.key}
              className={`flex flex-col items-center gap-1 p-2 rounded-lg transition-all duration-300 ${
                state === "active"
                  ? "bg-red-900/30 border border-red-800"
                  : state === "done"
                    ? "bg-zinc-800/50"
                    : "opacity-40"
              }`}
            >
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  state === "active"
                    ? "bg-red-600 text-white animate-pulse"
                    : state === "done"
                      ? "bg-green-600 text-white"
                      : "bg-zinc-700 text-zinc-500"
                }`}
              >
                {state === "done" ? "\u2713" : step.icon}
              </div>
              <span
                className={`text-[9px] text-center leading-tight ${
                  state === "active"
                    ? "text-red-400 font-medium"
                    : state === "done"
                      ? "text-zinc-400"
                      : "text-zinc-600"
                }`}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Animated scanner line effect */}
      <div className="relative h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-red-500 to-transparent animate-scan" />
      </div>

      <p className="text-[10px] text-zinc-600 text-center">
        YOLOv8-Pose skeleton tracking + biomechanical analysis + Claude AI
        coaching
      </p>

      <style jsx>{`
        @keyframes scan {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(200%);
          }
        }
        .animate-scan {
          animation: scan 2s ease-in-out infinite;
          width: 40%;
        }
      `}</style>
    </Card>
  );
}
