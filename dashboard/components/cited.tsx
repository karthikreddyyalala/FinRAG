"use client";
import { useState, useId } from "react";
import { getMetric } from "@/lib/metrics";

export function Cited({ metric: key }: { metric: string }) {
  const metric = getMetric(key as Parameters<typeof getMetric>[0]);
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={id}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        className="cursor-pointer border-b border-dashed border-[var(--color-muted)] font-[family-name:var(--font-mono)] tabular-nums transition-colors duration-200 hover:border-[var(--color-grounded)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-grounded)]"
      >
        {metric.display}
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute z-10 mt-2 w-64 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm text-[var(--color-muted)] shadow-[var(--shadow-card)]"
        >
          <strong className="block font-[family-name:var(--font-mono)] text-[var(--color-text)]">
            {metric.source_file}
          </strong>
          {metric.source_detail}
        </span>
      )}
    </span>
  );
}
