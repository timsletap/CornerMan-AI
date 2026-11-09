"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { GridIcon, LogoutIcon, SearchIcon, UploadIcon, UserIcon } from "@/components/ui/icons";

const NAV_LINKS = [
  { href: "/dashboard", label: "Camp", icon: GridIcon },
  { href: "/upload", label: "Upload", icon: UploadIcon },
  { href: "/search", label: "Find clips", icon: SearchIcon },
  { href: "/profile", label: "Profile", icon: UserIcon },
];

export function Navbar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <>
      <nav className="sticky top-0 z-50 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-10">
            <Link href="/dashboard" aria-label="CornerMan home">
              <Logo />
            </Link>
            <div className="hidden items-center gap-7 md:flex">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={isActive(link.href) ? "page" : undefined}
                  className={`relative py-5 font-display text-[0.9375rem] font-bold uppercase tracking-wider transition-colors
                    ${isActive(link.href) ? "text-chalk" : "text-mute hover:text-chalk"}`}
                >
                  {link.label}
                  {isActive(link.href) && (
                    <span className="absolute inset-x-0 -bottom-px h-0.5 bg-blood" />
                  )}
                </Link>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <ButtonLink href="/upload" size="sm" className="hidden sm:inline-flex">
              <UploadIcon /> Upload film
            </ButtonLink>
            {user && (
              <Link
                href="/profile"
                className="hidden items-center gap-2 text-sm text-mute hover:text-chalk lg:flex"
              >
                <span className="octagon flex h-7 w-7 items-center justify-center bg-panel-2 font-display text-sm font-bold text-chalk">
                  {user.full_name[0]?.toUpperCase()}
                </span>
                {user.full_name}
              </Link>
            )}
            <button
              onClick={logout}
              className="flex cursor-pointer items-center gap-1.5 text-sm text-mute transition-colors hover:text-chalk"
            >
              <LogoutIcon className="text-base" />
              <span className="hidden sm:inline">Log out</span>
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile bottom nav */}
      <div className="fixed inset-x-0 bottom-0 z-50 border-t border-line bg-canvas/95 backdrop-blur-md md:hidden">
        <div className="grid grid-cols-4">
          {NAV_LINKS.map(({ href, label, icon: NavIcon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={`flex flex-col items-center gap-1 py-2.5 font-mono text-[0.625rem] uppercase tracking-wider
                ${isActive(href) ? "text-blood" : "text-mute"}`}
            >
              <NavIcon className="text-xl" />
              {label}
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
