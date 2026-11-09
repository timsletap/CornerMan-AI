"use client";

import { type SelectHTMLAttributes, forwardRef } from "react";
import { fieldClasses } from "./input";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className = "", id, ...props }, ref) => {
    const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={selectId} className="eyebrow block">
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={`${fieldClasses} ${error ? "border-blood" : "border-line-2"} ${className}`}
          {...props}
        >
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && <p className="text-sm text-[#ff6b75]">{error}</p>}
      </div>
    );
  },
);

Select.displayName = "Select";
