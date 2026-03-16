import type { ReactNode } from "react";

const colorMap: Record<string, string> = {
  green: "bg-green-900/50 text-green-400 border-green-800",
  red: "bg-red-900/50 text-red-400 border-red-800",
  yellow: "bg-yellow-900/50 text-yellow-400 border-yellow-800",
  blue: "bg-blue-900/50 text-blue-400 border-blue-800",
  zinc: "bg-zinc-800 text-zinc-400 border-zinc-700",
  orange: "bg-orange-900/50 text-orange-400 border-orange-800",
};

export function Badge({
  children,
  color = "zinc",
  className = "",
}: {
  children: ReactNode;
  color?: keyof typeof colorMap;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${colorMap[color] || colorMap.zinc} ${className}`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: keyof typeof colorMap; label: string }> = {
    uploaded: { color: "blue", label: "Uploaded" },
    validating: { color: "yellow", label: "Validating" },
    validated: { color: "green", label: "Ready" },
    queued: { color: "yellow", label: "Queued" },
    processing: { color: "orange", label: "Processing" },
    completed: { color: "green", label: "Completed" },
    failed: { color: "red", label: "Failed" },
  };
  const { color, label } = map[status] || { color: "zinc" as const, label: status };
  return <Badge color={color}>{label}</Badge>;
}
