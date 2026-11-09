"use client";

import { useEffect, useState } from "react";
import {
  BONES,
  GUARD_GAP_LIMIT,
  JOINTS,
  LOOP_MS,
  STILL_MS,
  chinOf,
  guardGap,
  offHandOf,
  poseAt,
  type Point,
} from "@/lib/skeleton-pose";

const TRAIL_STEPS = [20, 40, 60, 80, 100];

function trail(ms: number, joint: "leadWrist" | "rearWrist"): Point[] {
  return TRAIL_STEPS.map((back) => poseAt(ms - back).pose[joint]);
}

/**
 * Animated pose skeleton throwing a jab-cross, drawn the way the analysis overlay draws a
 * fighter: joints, bones, a wrist trail, and the guard line from the off hand to the chin.
 */
export function SkeletonFighter({ className = "" }: { className?: string }) {
  const [ms, setMs] = useState(STILL_MS);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const start = performance.now() - STILL_MS;
    const tick = (now: number) => {
      setMs((now - start) % LOOP_MS);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const { pose, phase } = poseAt(ms);
  const punching = phase === "cross" ? "rearWrist" : "leadWrist";
  const offHand = offHandOf(pose, phase);
  const chin = chinOf(pose);
  const guardDown = guardGap(pose, phase) > GUARD_GAP_LIMIT;
  const guardColor = guardDown ? "#e8202f" : "#2fd27a";
  const fist = pose[punching];
  const neck: Point = [
    (pose.leadShoulder[0] + pose.rearShoulder[0]) / 2,
    (pose.leadShoulder[1] + pose.rearShoulder[1]) / 2,
  ];

  return (
    <svg
      viewBox="0 0 240 260"
      className={className}
      role="img"
      aria-label="Pose skeleton throwing a jab and a cross, with the guard line turning red when the lead hand drops"
    >
      {/* Mat */}
      <ellipse cx="112" cy="240" rx="78" ry="7" fill="#e8202f" opacity="0.12" />
      <line x1="10" y1="240" x2="230" y2="240" stroke="#383844" strokeWidth="1" />

      {/* Wrist trail of the punching hand */}
      {phase !== "guard" &&
        trail(ms, punching).map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={3.2 - i * 0.4} fill="#f3c24f" opacity={0.5 - i * 0.09} />
        ))}

      {/* Bones */}
      <g stroke="#f5f2ea" strokeWidth="3" strokeLinecap="round">
        {BONES.map(([a, b]) => (
          <line key={`${a}-${b}`} x1={pose[a][0]} y1={pose[a][1]} x2={pose[b][0]} y2={pose[b][1]} />
        ))}
        <line x1={neck[0]} y1={neck[1]} x2={pose.head[0]} y2={pose.head[1] + 11} />
      </g>
      <circle cx={pose.head[0]} cy={pose.head[1]} r="11" fill="#07070a" stroke="#f5f2ea" strokeWidth="3" />

      {/* Guard line: off hand to chin */}
      <line
        x1={offHand[0]}
        y1={offHand[1]}
        x2={chin[0]}
        y2={chin[1]}
        stroke={guardColor}
        strokeWidth="1.5"
        strokeDasharray="3 3"
      />

      {/* Joints */}
      {JOINTS.filter((joint) => joint !== "head").map((joint) => (
        <circle
          key={joint}
          cx={pose[joint][0]}
          cy={pose[joint][1]}
          r={joint.endsWith("Wrist") ? 4.5 : 3.2}
          fill={joint === punching && phase !== "guard" ? "#f3c24f" : "#e8202f"}
          stroke="#07070a"
          strokeWidth="1"
        />
      ))}

      {/* Strike call-out */}
      {phase !== "guard" && (
        <g transform={`translate(${Math.min(fist[0] - 22, 158)} ${fist[1] - 30})`}>
          <rect width="62" height="17" fill={phase === "jab" ? "#3f8cff" : "#e8202f"} />
          <text
            x="31"
            y="12.5"
            textAnchor="middle"
            fontSize="10"
            fontWeight="800"
            fill="#fff"
            style={{ fontFamily: "var(--font-barlow), sans-serif", letterSpacing: "0.12em" }}
          >
            {phase === "jab" ? "JAB · LEAD" : "CROSS · REAR"}
          </text>
        </g>
      )}

      {/* Guard read-out */}
      <g transform="translate(14 18)">
        <rect width="92" height="17" fill="#07070a" stroke={guardColor} strokeWidth="1" />
        <circle cx="9" cy="8.5" r="2.5" fill={guardColor} />
        <text
          x="17"
          y="12"
          fontSize="8.5"
          fill={guardColor}
          style={{ fontFamily: "var(--font-geist-mono), monospace", letterSpacing: "0.1em" }}
        >
          {guardDown ? "GUARD DOWN" : "GUARD UP"}
        </text>
      </g>
    </svg>
  );
}
