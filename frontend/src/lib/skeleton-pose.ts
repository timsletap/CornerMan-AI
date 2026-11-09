/**
 * A looping jab-cross for the animated skeleton on the landing page.
 *
 * Coordinates are in a 240 x 260 SVG viewBox, y down. The fighter is orthodox and faces
 * right, so the lead hand is the left hand. The jab is thrown with the guard up; on the
 * cross the lead hand drops, which is what the app flags as a dropped guard.
 */

export const JOINTS = [
  "head",
  "leadShoulder",
  "rearShoulder",
  "leadElbow",
  "rearElbow",
  "leadWrist",
  "rearWrist",
  "leadHip",
  "rearHip",
  "leadKnee",
  "rearKnee",
  "leadAnkle",
  "rearAnkle",
] as const;

export type Joint = (typeof JOINTS)[number];
export type Point = readonly [x: number, y: number];
export type Pose = Record<Joint, Point>;

export const BONES: readonly (readonly [Joint, Joint])[] = [
  ["leadShoulder", "rearShoulder"],
  ["leadShoulder", "leadElbow"],
  ["leadElbow", "leadWrist"],
  ["rearShoulder", "rearElbow"],
  ["rearElbow", "rearWrist"],
  ["leadShoulder", "leadHip"],
  ["rearShoulder", "rearHip"],
  ["leadHip", "rearHip"],
  ["leadHip", "leadKnee"],
  ["leadKnee", "leadAnkle"],
  ["rearHip", "rearKnee"],
  ["rearKnee", "rearAnkle"],
];

const GUARD: Pose = {
  head: [112, 50],
  leadShoulder: [124, 80],
  rearShoulder: [98, 82],
  leadElbow: [134, 106],
  rearElbow: [96, 110],
  leadWrist: [137, 76],
  rearWrist: [111, 72],
  leadHip: [118, 144],
  rearHip: [100, 146],
  leadKnee: [136, 186],
  rearKnee: [90, 190],
  leadAnkle: [142, 234],
  rearAnkle: [74, 236],
};

const JAB: Pose = {
  ...GUARD,
  head: [115, 50],
  leadShoulder: [129, 79],
  leadElbow: [160, 77],
  leadWrist: [192, 74],
  rearWrist: [113, 71],
  leadKnee: [139, 186],
};

const CROSS: Pose = {
  ...GUARD,
  head: [119, 52],
  leadShoulder: [116, 83],
  rearShoulder: [121, 79],
  leadElbow: [121, 111],
  leadWrist: [132, 100], // lead hand has dropped off the chin
  rearElbow: [157, 78],
  rearWrist: [193, 76],
  leadHip: [116, 145],
  rearHip: [108, 144],
  rearKnee: [103, 188],
  rearAnkle: [77, 232],
};

export type Phase = "guard" | "jab" | "cross";

interface Segment {
  /** Segment end time in ms from the start of the loop. */
  until: number;
  from: Pose;
  to: Pose;
  ease: (t: number) => number;
  phase: Phase;
}

const easeOut = (t: number) => 1 - (1 - t) ** 3;
const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

const SEGMENTS: readonly Segment[] = [
  { until: 700, from: GUARD, to: GUARD, ease: easeInOut, phase: "guard" },
  { until: 820, from: GUARD, to: JAB, ease: easeOut, phase: "jab" },
  { until: 920, from: JAB, to: JAB, ease: easeInOut, phase: "jab" },
  { until: 1100, from: JAB, to: GUARD, ease: easeInOut, phase: "guard" },
  { until: 1250, from: GUARD, to: CROSS, ease: easeOut, phase: "cross" },
  { until: 1380, from: CROSS, to: CROSS, ease: easeInOut, phase: "cross" },
  { until: 1640, from: CROSS, to: GUARD, ease: easeInOut, phase: "guard" },
  { until: 2700, from: GUARD, to: GUARD, ease: easeInOut, phase: "guard" },
];

export const LOOP_MS = SEGMENTS[SEGMENTS.length - 1].until;
/** A moment with the jab fully extended; used as the still frame. */
export const STILL_MS = 870;

function lerp(a: Point, b: Point, t: number): Point {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Pose and phase at `ms` into the loop (any value; it wraps). */
export function poseAt(ms: number): { pose: Pose; phase: Phase } {
  const t = ((ms % LOOP_MS) + LOOP_MS) % LOOP_MS;
  let start = 0;
  for (const segment of SEGMENTS) {
    if (t < segment.until) {
      const progress = segment.ease((t - start) / (segment.until - start));
      const pose = {} as Record<Joint, Point>;
      for (const joint of JOINTS) {
        pose[joint] = lerp(segment.from[joint], segment.to[joint], progress);
      }
      return { pose, phase: segment.phase };
    }
    start = segment.until;
  }
  return { pose: GUARD, phase: "guard" };
}

export function chinOf(pose: Pose): Point {
  return [pose.head[0] + 4, pose.head[1] + 12];
}

function gap(a: Point, b: Point): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

/**
 * The hand that should be guarding the chin: the non-punching hand during a punch, and
 * between punches whichever hand is closer (the other may still be on its way back).
 */
export function offHandOf(pose: Pose, phase: Phase): Point {
  if (phase === "jab") return pose.rearWrist;
  if (phase === "cross") return pose.leadWrist;
  const chin = chinOf(pose);
  return gap(pose.leadWrist, chin) <= gap(pose.rearWrist, chin) ? pose.leadWrist : pose.rearWrist;
}

/** Distance in viewBox units from the off hand to the chin. */
export function guardGap(pose: Pose, phase: Phase): number {
  return gap(offHandOf(pose, phase), chinOf(pose));
}

/** Above this gap the guard line turns red. */
export const GUARD_GAP_LIMIT = 30;
