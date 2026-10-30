"use client";
import { getMetric } from "@/lib/metrics";
import { Cited } from "@/components/cited";

export function CostLatency() {
  const missMs = getMetric("warm_search_p50_ms");
  const hitMs = getMetric("cache_hit_p50_ms");
  const speedup = (missMs.value / hitMs.value).toFixed(1);

  return (
    <section className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Cost and latency.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Measured against the live server on 2026-10-30, 10 searches. A warm search takes{" "}
          <Cited metric="warm_search_p50_ms" /> at the median, and the slowest of the 10 took{" "}
          <Cited metric="warm_search_max_ms" />. One search costs about <Cited metric="cost_per_search_usd" />, an
          estimate from Lambda time plus one embedding, not a bill. There is no chat model cost, because the server
          runs none.
        </p>

        <div className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <h3 className="font-semibold text-[var(--color-text)]">
            The cache race: {speedup}x faster on a repeat call
          </h3>
          <div className="mt-6 space-y-4">
            <div>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-[var(--color-muted)]">Cache miss (warm)</span>
                <Cited metric="warm_search_p50_ms" />
              </div>
              <div className="mt-1.5 h-3 rounded-full bg-[var(--color-elevated)]">
                <div className="h-3 w-full rounded-full bg-[var(--color-border)]" />
              </div>
            </div>
            <div>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-[var(--color-muted)]">Cache hit</span>
                <Cited metric="cache_hit_p50_ms" />
              </div>
              <div className="mt-1.5 h-3 rounded-full bg-[var(--color-elevated)]">
                <div
                  className="h-3 rounded-full bg-[var(--color-grounded)]"
                  style={{ width: `${(hitMs.value / missMs.value) * 100}%` }}
                />
              </div>
            </div>
          </div>
          <p className="mt-6 max-w-[65ch] border-t border-[var(--color-border)] pt-4 text-sm text-[var(--color-muted)]">
            The first call after a deploy is slow: <Cited metric="cold_first_call_ms" /> server-side, because the
            Lambda loads the 964 MB keyword index. After that the function stays warm.
          </p>
        </div>
      </div>
    </section>
  );
}
