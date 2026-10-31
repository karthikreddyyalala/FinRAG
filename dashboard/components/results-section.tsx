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
            End to end, the way a user meets it: a model calls the real tools in a loop, as Claude or Cursor would,
            and each answer is scored right, wrong or refused against FinanceBench&apos;s answer key. gpt-4o-mini
            plays the client.
          </p>
          <table className="mt-4 w-full min-w-[480px] text-left text-sm">
            <thead className="text-[var(--color-muted)]">
              <tr className="border-b border-[var(--color-border)]">
                <th className="py-2 pr-4 font-medium">Agent test, 2026-10-30</th>
                <th className="py-2 pr-4 font-medium">Search only</th>
                <th className="py-2 font-medium">+ exact figures (live)</th>
              </tr>
            </thead>
            <tbody className="font-[family-name:var(--font-mono)] tabular-nums">
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">FinanceBench right (of 110)</td>
                <td className="py-2 pr-4">67</td>
                <td className="py-2 text-[var(--color-grounded)]">92</td>
              </tr>
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Wrong</td>
                <td className="py-2 pr-4">21</td>
                <td className="py-2 text-[var(--color-grounded)]">14</td>
              </tr>
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Refused</td>
                <td className="py-2 pr-4">22</td>
                <td className="py-2 text-[var(--color-grounded)]">4</td>
              </tr>
              <tr>
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Fourth-quarter set right / wrong (of 48)</td>
                <td className="py-2 pr-4">13 / 32</td>
                <td className="py-2 text-[var(--color-grounded)]">39 / 7</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-3 mb-10 max-w-[65ch] text-sm text-[var(--color-muted)]">
            Exact figures come from the XBRL data in each filing, for any US-listed company. Searching passages, the
            model had to find one table row among 171,790 chunks; most of its fourth-quarter answers reported the
            full year, since no filing states a Q4 on its own. The figures tool derives Q4 and says how.
          </p>
          <p className="max-w-[65ch] text-[var(--color-muted)]">
            The one-shot test isolates retrieval: one search, five passages, one answer. Re-measured on 2026-10-30: the same 150 FinanceBench questions through the live server&apos;s retrieval,
            answers written by gpt-4o-mini, September answers re-scored with the same code. Automated checks, not
            hand-graded. &ldquo;Voyage rerank&rdquo; is the same server with a neural reranker over 40 candidates per
            search instead of a word-overlap scorer over 10.
          </p>
          <table className="mt-4 w-full min-w-[640px] text-left text-sm">
            <thead className="text-[var(--color-muted)]">
              <tr className="border-b border-[var(--color-border)]">
                <th className="py-2 pr-4 font-medium">FinanceBench, 150 questions</th>
                <th className="py-2 pr-4 font-medium">September</th>
                <th className="py-2 pr-4 font-medium">Word-overlap rerank</th>
                <th className="py-2 pr-4 font-medium">Voyage rerank</th>
                <th className="py-2 font-medium">+ clean tables (live)</th>
              </tr>
            </thead>
            <tbody className="font-[family-name:var(--font-mono)] tabular-nums">
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Refused to answer</td>
                <td className="py-2 pr-4">121</td>
                <td className="py-2 pr-4">99</td>
                <td className="py-2 pr-4">55</td>
                <td className="py-2 text-[var(--color-grounded)]">61</td>
              </tr>
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Right number (of 110)</td>
                <td className="py-2 pr-4">16</td>
                <td className="py-2 pr-4">26</td>
                <td className="py-2 pr-4">54</td>
                <td className="py-2 text-[var(--color-grounded)]">53</td>
              </tr>
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Wrong number (of 110)</td>
                <td className="py-2 pr-4">4</td>
                <td className="py-2 pr-4">9</td>
                <td className="py-2 pr-4">14</td>
                <td className="py-2 text-[var(--color-grounded)]">9</td>
              </tr>
              <tr className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Evidence passage in the top 5 (of 127)</td>
                <td className="py-2 pr-4">not measured</td>
                <td className="py-2 pr-4">13.4%</td>
                <td className="py-2 pr-4">45.7%</td>
                <td className="py-2 text-[var(--color-grounded)]">46.5%</td>
              </tr>
              <tr>
                <td className="py-2 pr-4 font-[family-name:var(--font-body)]">Every figure found in its sources</td>
                <td className="py-2 pr-4">not measured</td>
                <td className="py-2 pr-4">96.7%</td>
                <td className="py-2 pr-4">84%</td>
                <td className="py-2 text-[var(--color-grounded)]">85.3%</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-3 max-w-[65ch] text-sm text-[var(--color-muted)]">
            Clean tables raised refusals from 55 to 61 and cut wrong answers from 14 to 9: 17 of the 18 answers
            that became refusals had been wrong, mostly a full-year figure reported as a quarter. A wrong figure is
            worse than a refusal, so refusals alone are the wrong scoreboard. The figure check is lower than before
            because more answers compute ratios or convert units, which it does not do by design.
            The charts below are the September pipeline.
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
