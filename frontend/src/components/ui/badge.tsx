import type { ReactNode } from "react";

const colorMap = {
  green: "border-go/40 bg-go/10 text-go",
  red: "border-blood/50 bg-blood/10 text-[#ff6b75]",
  yellow: "border-gold/40 bg-gold/10 text-gold",
  blue: "border-corner/40 bg-corner/10 text-[#7db1ff]",
  zinc: "border-line-2 bg-white/5 text-mute",
  orange: "border-[#ff8a3d]/40 bg-[#ff8a3d]/10 text-[#ff8a3d]",
} as const;

export type BadgeColor = keyof typeof colorMap;

export function Badge({
  children,
  color = "zinc",
  className = "",
}: {
  children: ReactNode;
  color?: BadgeColor;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-[0.6875rem] uppercase tracking-wider ${colorMap[color]} ${className}`}
    >
      {children}
    </span>
  );
}

const statusMap: Record<string, { color: BadgeColor; label: string; live?: boolean }> = {
  uploaded: { color: "blue", label: "Uploaded" },
  validating: { color: "yellow", label: "Checking", live: true },
  validated: { color: "green", label: "Ready" },
  queued: { color: "yellow", label: "In queue", live: true },
  processing: { color: "orange", label: "Analyzing", live: true },
  completed: { color: "green", label: "Complete" },
  failed: { color: "red", label: "Failed" },
};

export function StatusBadge({ status }: { status: string }) {
  const { color, label, live } = statusMap[status] ?? { color: "zinc" as const, label: status };
  return (
    <Badge color={color}>
      {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {label}
    </Badge>
  );
}
