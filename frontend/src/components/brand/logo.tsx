/** Octagon mark: a cage seen from above, with a C for the corner. */
export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <polygon points="12,1 28,1 39,12 39,28 28,39 12,39 1,28 1,12" fill="#e8202f" />
      <polygon
        points="13.5,5.5 26.5,5.5 34.5,13.5 34.5,26.5 26.5,34.5 13.5,34.5 5.5,26.5 5.5,13.5"
        fill="none"
        stroke="#07070a"
        strokeWidth="1.5"
      />
      <path
        d="M24.5 14.5a6.5 6.5 0 1 0 0 11"
        fill="none"
        stroke="#fff"
        strokeWidth="3.4"
        strokeLinecap="square"
      />
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`display text-2xl leading-none text-chalk ${className}`}>
      Corner<span className="text-blood">Man</span>
    </span>
  );
}

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark />
      <Wordmark />
    </span>
  );
}
