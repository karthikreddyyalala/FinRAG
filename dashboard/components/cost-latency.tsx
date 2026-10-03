"use client";
import { getMetric } from "@/lib/metrics";
import { Cited } from "@/components/cited";

export function CostLatency() {
  const missMs = getMetric("cache_miss_latency_ms");
  const hitMs = getMetric("cache_hit_latency_ms");
  const speedup = Math.round(missMs.value / hitMs.value);
  const maxMs = missMs.value;

  return (
    <section className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Cost and latency.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Average cost per query: <Cited metric="avg_cost_per_query" /> · Average latency:{" "}
          <Cited metric="avg_latency_ms" />, measured on a fixed 15-question set against real production
          dependencies.
        </p>

        <div className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <h3 className="font-semibold text-[var(--color-text)]">
            The cache race: {speedup}x faster on a repeat question
          </h3>
          <div className="mt-6 space-y-4">
            <div>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-[var(--color-muted)]">Cache miss</span>
                <Cited metric="cache_miss_latency_ms" />
              </div>
              <div className="mt-1.5 h-3 rounded-full bg-[var(--color-elevated)]">
                <div className="h-3 w-full rounded-full bg-[var(--color-border)]" />
              </div>
            </div>
            <div>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-[var(--color-muted)]">Cache hit</span>
                <Cited metric="cache_hit_latency_ms" />
              </div>
              <div className="mt-1.5 h-3 rounded-full bg-[var(--color-elevated)]">
                <div
                  className="h-3 rounded-full bg-[var(--color-grounded)]"
                  style={{ width: `${Math.max(1, (hitMs.value / maxMs) * 100)}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
