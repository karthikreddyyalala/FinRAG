"use client";
import { getMetric } from "@/lib/metrics";
import { DataTableFallback } from "@/components/charts/data-table-fallback";

const ROWS = [
  { label: "Numerical accuracy", fb: "numerical_accuracy_financebench", custom: "numerical_accuracy_custom" },
  { label: "Faithfulness", fb: "faithfulness_financebench", custom: "faithfulness_custom" },
] as const;

export function FinanceBenchVsCustomChart() {
  return (
    <div>
      <h3 className="font-semibold text-[var(--color-text)]">FinanceBench vs. hand-verified custom set</h3>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        150 public FinanceBench questions vs. 48 questions whose ground truth was independently verified against
        real SEC filing text.
      </p>

      <div className="mt-6 space-y-6">
        {ROWS.map((row) => {
          const fb = getMetric(row.fb);
          const custom = getMetric(row.custom);
          const fbPct = fb.value * 100;
          const customPct = custom.value * 100;
          const left = Math.min(fbPct, customPct);
          const width = Math.abs(fbPct - customPct);
          return (
            <div key={row.label}>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-[var(--color-text)]">{row.label}</span>
                <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-muted)]">
                  FinanceBench {fb.display} · Custom {custom.display}
                </span>
              </div>
              <div className="relative mt-2 h-1.5 rounded-full bg-[var(--color-elevated)]">
                <div
                  className="absolute h-1.5 rounded-full bg-[var(--color-border)]"
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
                <div
                  className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-[var(--color-bg)] bg-[var(--color-grounded)]"
                  style={{ left: `calc(${fbPct}% - 6px)` }}
                  aria-hidden
                />
                <div
                  className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-[var(--color-bg)] bg-[var(--color-text)]"
                  style={{ left: `calc(${customPct}% - 6px)` }}
                  aria-hidden
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex gap-4 text-xs text-[var(--color-muted)]">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--color-grounded)]" /> FinanceBench
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--color-text)]" /> Custom verified
        </span>
      </div>

      <DataTableFallback
        caption="FinanceBench vs custom verified"
        columns={["Metric", "FinanceBench", "Custom verified"]}
        rows={ROWS.map((row) => [row.label, getMetric(row.fb).display, getMetric(row.custom).display])}
      />
    </div>
  );
}
