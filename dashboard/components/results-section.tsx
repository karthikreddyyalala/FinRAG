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

        <div className="mt-8 overflow-x-auto">
          <p className="max-w-[65ch] text-[var(--color-muted)]">
            Re-measured on 2026-10-30: the same 150 FinanceBench questions through the live server&apos;s retrieval,
            answers written by gpt-4o-mini, September answers re-scored with the same code. Automated checks, not
            hand-graded.
          </p>
          <table className="mt-4 w-full min-w-[480px] text-left text-sm">
            <thead className="text-[var(--color-muted)]">
              <tr className="border-b border-[var(--color-border)]">
                <th className="py-2 pr-4 font-medium">FinanceBench, 150 questions</th>
                <th className="py-2 pr-4 font-medium">September</th>
                <th className="py-2 font-medium">Now</th>
              </tr>
            </thead>
            <tbody className="font-[family-name:var(--font-mono)] tabular-nums">
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Refused to answer</td>
                <td className="py-2 pr-4">121</td>
                <td className="py-2 text-[var(--color-grounded)]">99</td>
              </tr>
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Right number, among answered (of 110)</td>
                <td className="py-2 pr-4">15</td>
                <td className="py-2 text-[var(--color-grounded)]">25</td>
              </tr>
              <tr>
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Every figure found in its sources</td>
                <td className="py-2 pr-4">not measured</td>
                <td className="py-2 text-[var(--color-grounded)]">96.7%</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-3 max-w-[65ch] text-sm text-[var(--color-muted)]">
            It still refuses about two in three questions, mostly ratio questions where retrieval misses a statement
            line. The charts below are the September pipeline.
          </p>
        </div>

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
              honest loss. The metric is the problem. Numerical accuracy asks what fraction of the numbers an
              answer states are grounded, and an answer with no numbers in it scores a perfect 1.0, so refusing
              raises the score. BM25-only refused the most (133 of 150, against 121 for the other two). But that
              explains only part of its lead. On a rough check of whether the answer states the correct number,
              the three setups land within noise of each other (52, 48 and 52 of 110, a count that also included stray numbers inside refusals). So this benchmark cannot
              rank them either way. The lesson is to ask what a do-nothing system would score before trusting a
              metric.
            </p>
          </div>
          <div className="border-l-2 border-[var(--color-flagged)] pl-5">
            <h3 className="font-semibold text-[var(--color-flagged)]">What we can&apos;t explain yet</h3>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Answer relevancy, context precision and context recall score low (about 10 to 20%). Part of that is
              explained: about four in five answers were refusals, and ragas scores a refusal as zero relevancy;
              about 28 of 150 questions need years the corpus doesn&apos;t hold; and in a rough check the right
              chunk was in the top five only about half the time. Whether the metrics also fit this task badly
              (terse numeric answers judged against long table chunks) is untested.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
