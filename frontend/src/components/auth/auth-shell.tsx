import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/brand/logo";
import { SkeletonFighter } from "@/components/landing/skeleton-fighter";

/** Two-column frame for the sign-in and sign-up pages: poster on the left, form on the right. */
export function AuthShell({
  eyebrow,
  title,
  children,
  footer,
}: {
  eyebrow: string;
  title: ReactNode;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-line bg-panel/60 p-10 lg:flex">
        <Link href="/" aria-label="CornerMan home">
          <Logo />
        </Link>
        <SkeletonFighter className="mx-auto w-full max-w-sm" />
        <div>
          <p className="display text-5xl text-chalk">
            Film doesn&apos;t lie.
            <br />
            <span className="text-blood">Neither do we.</span>
          </p>
          <p className="mt-3 max-w-md text-mute">
            Every punch logged, every dropped guard flagged, one thing to fix before your
            next round.
          </p>
        </div>
      </aside>

      <main className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md animate-rise">
          <Link href="/" className="mb-10 inline-block lg:hidden" aria-label="CornerMan home">
            <Logo />
          </Link>
          <p className="eyebrow mb-2 text-blood">{eyebrow}</p>
          <h1 className="display mb-8 text-5xl text-chalk">{title}</h1>
          {children}
          <p className="mt-6 text-sm text-mute">{footer}</p>
        </div>
      </main>
    </div>
  );
}
