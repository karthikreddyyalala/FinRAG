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
            <h3 className="font-semibold text-[var(--color-flagged)]">Where the metric lied</h3>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              BM25-only scores <em>higher</em> here than the full pipeline, and for a while I published that as an
              honest loss. It was a measurement artifact. Numerical accuracy asks what fraction of the numbers an
              answer states are grounded, and an answer with no numbers in it scores a perfect 1.0, so the metric
              is maximised by refusing. BM25-only refuses the most (133 of 150, against 121 for the other two),
              which is exactly why it came first. Scored on whether the answer actually states the number the
              ground truth says it should, the ordering reverses: full pipeline 47.3%, dense-only 47.3%,
              BM25-only 43.6%. A precision metric with no recall term can be gamed by silence.
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
