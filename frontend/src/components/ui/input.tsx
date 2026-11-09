"use client";

import { type InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const fieldClasses =
  "h-11 w-full rounded-sm border bg-canvas/70 px-3 text-chalk placeholder:text-dim transition-colors focus:border-blood focus:outline-none focus:ring-1 focus:ring-blood";

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = "", id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={inputId} className="eyebrow block">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`${fieldClasses} ${error ? "border-blood" : "border-line-2"} ${className}`}
          {...props}
        />
        {error && <p className="text-sm text-[#ff6b75]">{error}</p>}
      </div>
    );
  },
);

Input.displayName = "Input";
