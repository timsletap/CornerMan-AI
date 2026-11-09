export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizeClasses = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" };
  return (
    <div
      className={`animate-spin rounded-full border-2 border-line-2 border-t-blood ${sizeClasses[size]}`}
      role="status"
    >
      <span className="sr-only">Loading...</span>
    </div>
  );
}

/** Centered spinner for a page or panel that is still loading. */
export function LoadingBlock({ fullScreen = false }: { fullScreen?: boolean }) {
  return (
    <div className={`flex items-center justify-center ${fullScreen ? "min-h-screen" : "py-24"}`}>
      <Spinner size={fullScreen ? "lg" : "md"} />
    </div>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-sm border border-blood/50 bg-blood/10 px-3 py-2.5 text-sm text-[#ff8f97]"
    >
      {children}
    </div>
  );
}
