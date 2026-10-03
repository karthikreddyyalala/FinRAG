"use client";
import dynamic from "next/dynamic";

const BaselineComparisonChart = dynamic(
  () => import("@/components/charts/baseline-comparison-chart").then((m) => m.BaselineComparisonChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const FinanceBenchVsCustomChart = dynamic(
  () => import("@/components/charts/financebench-vs-custom-chart").then((m) => m.FinanceBenchVsCustomChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);

function ChartSkeleton() {
  return <div className="h-64 animate-pulse rounded-2xl bg-[var(--color-elevated)]" />;
}

export function ResultsSection() {
  return (
    <section id="results" className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Measured, not claimed.
        </h2>

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
            <BaselineComparisonChart />
          </div>
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
            <FinanceBenchVsCustomChart />
          </div>
        </div>

        <div className="mt-12 grid gap-8 md:grid-cols-2">
          <div className="border-l-2 border-[var(--color-flagged)] pl-5">
            <h3 className="font-semibold text-[var(--color-flagged)]">Where it lost</h3>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              On this benchmark, BM25-only retrieval alone scores <em>higher</em> than the full four-stage pipeline
              on numerical accuracy and faithfulness. FinanceBench&apos;s questions are largely keyword-friendly,
              close to how filings actually word things, which favors lexical search directly. What the full
              pipeline demonstrably buys over dense-only search is a real gap in numerical accuracy and context
              recall; whether the added complexity is worth it specifically for FinanceBench-style questions is an
              open finding, not a foregone conclusion.
            </p>
          </div>
          <div className="border-l-2 border-[var(--color-flagged)] pl-5">
            <h3 className="font-semibold text-[var(--color-flagged)]">What we can&apos;t explain yet</h3>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Three ragas metrics (answer relevancy, context precision, context recall) score consistently low
              (2–20%) across every complete eval run, including after independently verifying that retrieval finds
              the exact correct source chunk and number for spot-checked questions. The working theory is that
              ragas&apos;s LLM-judged metrics are a poor fit for this task shape: terse numeric ground truths scored
              against long, pipe-delimited financial table chunks. Stated as an open question, not resolved.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
