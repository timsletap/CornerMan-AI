import { guardGrade, type GuardTone } from "@/lib/fight-stats";

const toneColor: Record<GuardTone, string> = {
  good: "#2fd27a",
  warn: "#f3c24f",
  bad: "#e8202f",
  none: "#62626e",
};

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Guard score (0 to 100) as a ring gauge with a one-word verdict. */
export function GuardRing({ score, size = 148 }: { score: number | null; size?: number }) {
  const { tone, label } = guardGrade(score);
  const color = toneColor[tone];
  const filled = score === null ? 0 : Math.min(100, Math.max(0, score)) / 100;

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={score === null ? "Guard score not available" : `Guard score ${Math.round(score)} percent, ${label}`}
    >
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={RADIUS} fill="none" stroke="#25252e" strokeWidth="8" />
        <circle
          cx="60"
          cy="60"
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={`${CIRCUMFERENCE * filled} ${CIRCUMFERENCE}`}
          style={{ transition: "stroke-dasharray 0.9s cubic-bezier(0.2, 0.7, 0.2, 1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="display text-5xl text-chalk">
          {score === null ? "--" : Math.round(score)}
          {score !== null && <span className="text-2xl text-mute">%</span>}
        </p>
        <p className="eyebrow mt-0.5" style={{ color }}>
          {label}
        </p>
      </div>
    </div>
  );
}

/** Guard scores over time, oldest to newest, as a small line chart. */
export function GuardSparkline({ values, className = "" }: { values: number[]; className?: string }) {
  if (values.length < 2) return null;
  const width = 200;
  const height = 48;
  const step = width / (values.length - 1);
  // Zoom the y axis to the scores present (always including the 80% line) so a real
  // change in guard reads as a slope instead of a flat line.
  const floor = Math.max(0, Math.min(...values, 80) - 10);
  const y = (v: number) =>
    height - 4 - ((Math.min(100, Math.max(floor, v)) - floor) / (100 - floor)) * (height - 8);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values[values.length - 1];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      role="img"
      aria-label={`Guard score across your last ${values.length} analyses, latest ${Math.round(last)} percent`}
    >
      <line x1="0" x2={width} y1={y(80)} y2={y(80)} stroke="#2fd27a" strokeOpacity="0.35" strokeDasharray="3 4" />
      <polyline points={points} fill="none" stroke="#e8202f" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={width} cy={y(last)} r="3" fill="#f5f2ea" />
    </svg>
  );
}
