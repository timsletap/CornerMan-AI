"use client";

import Link from "next/link";
import { type ButtonHTMLAttributes, type ComponentProps, forwardRef } from "react";

const variants = {
  primary:
    "chamfer bg-blood text-white hover:bg-[#ff3040] active:bg-blood-deep shadow-[0_0_28px_-6px_rgb(232_32_47/0.7)]",
  secondary: "chamfer bg-chalk text-canvas hover:bg-white",
  outline: "border border-line-2 text-chalk hover:border-chalk/60 hover:bg-white/5",
  ghost: "text-mute hover:text-chalk hover:bg-white/5",
  danger: "border border-blood/40 text-blood hover:bg-blood/10",
} as const;

const sizes = {
  sm: "h-8 px-3 text-[0.8125rem]",
  md: "h-10 px-5 text-[0.9375rem]",
  lg: "h-13 px-8 text-lg",
} as const;

type Variant = keyof typeof variants;
type Size = keyof typeof sizes;

export function buttonClasses(variant: Variant = "primary", size: Size = "md", className = "") {
  return `inline-flex items-center justify-center gap-2 whitespace-nowrap font-display font-bold uppercase tracking-wider
    transition-colors duration-150 cursor-pointer
    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-chalk
    disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none
    ${variants[variant]} ${sizes[size]} ${className}`;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className = "", type = "button", ...props }, ref) => (
    <button ref={ref} type={type} className={buttonClasses(variant, size, className)} {...props} />
  ),
);

Button.displayName = "Button";

interface ButtonLinkProps extends ComponentProps<typeof Link> {
  variant?: Variant;
  size?: Size;
}

/** A link that looks like a button. Use for navigation instead of a button inside a link. */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonLinkProps) {
  return <Link className={buttonClasses(variant, size, className)} {...props} />;
}
