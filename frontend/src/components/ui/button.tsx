"use client";

import { type ButtonHTMLAttributes, forwardRef } from "react";

const variants = {
  primary: "bg-red-600 hover:bg-red-700 text-white",
  secondary: "bg-zinc-700 hover:bg-zinc-600 text-white",
  outline: "border border-zinc-600 hover:bg-zinc-800 text-zinc-200",
  ghost: "hover:bg-zinc-800 text-zinc-300",
  danger: "bg-red-800 hover:bg-red-900 text-white",
} as const;

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
} as const;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className = "", disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors
        focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 focus:ring-offset-zinc-900
        disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  ),
);

Button.displayName = "Button";
