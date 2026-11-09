import { formatBytes, formatDuration } from "./format";

// Mirrors the backend defaults (MAX_VIDEO_SIZE_MB, MAX_VIDEO_DURATION_SECONDS). The server
// is the authority; these checks only save the user a wasted upload.
export const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;
export const MAX_DURATION_SECONDS = 1800;
const MIN_SHORT_SIDE_PX = 480;

export interface ClipFacts {
  name: string;
  /** MIME type reported by the browser; may be empty. */
  type: string;
  sizeBytes: number;
  /** Null when the browser could not read the clip's metadata. */
  durationSeconds: number | null;
  /** Frame size in pixels; null when unknown. */
  width: number | null;
  height: number | null;
}

export type CheckStatus = "pass" | "warn" | "fail";

export interface ClipCheck {
  id: "format" | "size" | "length" | "framing" | "resolution";
  label: string;
  status: CheckStatus;
  detail: string;
}

const ALLOWED_TYPES = new Set(["video/mp4", "video/quicktime"]);

export function isAllowedFormat(name: string, type: string): boolean {
  return /\.(mp4|mov)$/i.test(name) || ALLOWED_TYPES.has(type);
}

/** Pre-upload checks for a clip. A `fail` blocks the upload; a `warn` only advises. */
export function checkClip(facts: ClipFacts): ClipCheck[] {
  const checks: ClipCheck[] = [];

  const formatOk = isAllowedFormat(facts.name, facts.type);
  checks.push({
    id: "format",
    label: "Format",
    status: formatOk ? "pass" : "fail",
    detail: formatOk ? "MP4 or MOV" : "Only .mp4 and .mov clips are supported",
  });

  const sizeOk = facts.sizeBytes <= MAX_UPLOAD_BYTES;
  checks.push({
    id: "size",
    label: "File size",
    status: sizeOk ? "pass" : "fail",
    detail: sizeOk
      ? formatBytes(facts.sizeBytes)
      : `${formatBytes(facts.sizeBytes)} is over the ${formatBytes(MAX_UPLOAD_BYTES)} limit`,
  });

  if (facts.durationSeconds === null) {
    checks.push({
      id: "length",
      label: "Length",
      status: "warn",
      detail: "Can't preview this clip here; it will be checked after upload",
    });
  } else {
    const lengthOk = facts.durationSeconds <= MAX_DURATION_SECONDS;
    checks.push({
      id: "length",
      label: "Length",
      status: lengthOk ? "pass" : "fail",
      detail: lengthOk
        ? formatDuration(facts.durationSeconds)
        : `${formatDuration(facts.durationSeconds)} is over the ${MAX_DURATION_SECONDS / 60} minute limit`,
    });
  }

  if (facts.width !== null && facts.height !== null) {
    const landscape = facts.width >= facts.height;
    checks.push({
      id: "framing",
      label: "Framing",
      status: landscape ? "pass" : "warn",
      detail: landscape
        ? "Landscape"
        : "Portrait clip; landscape keeps the whole fighter in frame",
    });

    const shortSide = Math.min(facts.width, facts.height);
    const sharp = shortSide >= MIN_SHORT_SIDE_PX;
    checks.push({
      id: "resolution",
      label: "Resolution",
      status: sharp ? "pass" : "warn",
      detail: sharp
        ? `${facts.width} x ${facts.height}`
        : `${facts.width} x ${facts.height} is low; tracking is steadier at 480p and up`,
    });
  }

  return checks;
}

export function canUpload(checks: ClipCheck[]): boolean {
  return checks.every((check) => check.status !== "fail");
}
