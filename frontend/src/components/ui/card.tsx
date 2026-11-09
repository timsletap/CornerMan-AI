import type { HTMLAttributes, ReactNode } from "react";

const accents = {
  none: "",
  blood: "before:bg-blood",
  gold: "before:bg-gold",
  corner: "before:bg-corner",
} as const;

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** Colored bar down the left edge. */
  accent?: keyof typeof accents;
}

export function Card({ children, className = "", accent = "none", ...props }: CardProps) {
  const bar =
    accent === "none"
      ? ""
      : `before:absolute before:inset-y-0 before:left-0 before:w-[3px] ${accents[accent]}`;
  return (
    <div
      className={`relative overflow-hidden rounded-md border border-line bg-panel/85 p-5 backdrop-blur-sm ${bar} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h3 className={`display text-2xl text-chalk ${className}`}>{children}</h3>;
}

/** Section header: a small label over a poster-type title, with an optional action. */
export function SectionHeading({
  eyebrow,
  title,
  action,
  className = "",
}: {
  eyebrow?: string;
  title: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-end justify-between gap-4 ${className}`}>
      <div>
        {eyebrow && <p className="eyebrow mb-1.5 text-blood">{eyebrow}</p>}
        <h2 className="display text-3xl text-chalk sm:text-4xl">{title}</h2>
      </div>
      {action}
    </div>
  );
}
