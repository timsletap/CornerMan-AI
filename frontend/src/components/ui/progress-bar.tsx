export function ProgressBar({ value, className = "" }: { value: number; className?: string }) {
  return (
    <div className={`h-2 w-full rounded-full bg-zinc-800 overflow-hidden ${className}`}>
      <div
        className="h-full rounded-full bg-red-600 transition-all duration-300"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
