import type { ErrorType, StrikeType } from "./types";

interface StrikeMeta {
  label: string;
  /** Hex color used for timeline markers, bars, and tags. */
  color: string;
}

export const STRIKE_META: Record<StrikeType, StrikeMeta> = {
  jab: { label: "Jab", color: "#3f8cff" },
  cross: { label: "Cross", color: "#e8202f" },
  hook: { label: "Hook", color: "#ff8a3d" },
  uppercut: { label: "Uppercut", color: "#f3c24f" },
  body_shot: { label: "Body shot", color: "#2fd27a" },
  elbow: { label: "Elbow", color: "#c77dff" },
  knee: { label: "Knee", color: "#c77dff" },
  kick: { label: "Kick", color: "#22d3ee" },
  other: { label: "Other", color: "#8d8d99" },
};

export function strikeMeta(type: string): StrikeMeta {
  return STRIKE_META[type as StrikeType] ?? STRIKE_META.other;
}

interface ErrorMeta {
  label: string;
  /** One line a fighter would say out loud for what went wrong. */
  blurb: string;
}

export const ERROR_META: Record<ErrorType, ErrorMeta> = {
  dropped_guard: {
    label: "Dropped guard",
    blurb: "Off hand left your chin while you punched",
  },
  chicken_wing: {
    label: "Telegraph",
    blurb: "Elbow flared before the punch left",
  },
  other: { label: "Flag", blurb: "Something looked off here" },
};

export function errorMeta(type: string): ErrorMeta {
  return ERROR_META[type as ErrorType] ?? ERROR_META.other;
}
