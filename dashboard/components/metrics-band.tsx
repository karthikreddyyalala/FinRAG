import { getMetric } from "@/lib/metrics";
import { Cited } from "@/components/cited";
import { CountUp } from "@/components/count-up";
import { TickerMarquee } from "@/components/ticker-marquee";

function Stat({ metricKey, label }: { metricKey: string; label: string }) {
  return (
    <div className="border-t border-[var(--color-border)] pt-4">
      <div className="font-[family-name:var(--font-mono)] text-3xl font-semibold tabular-nums text-[var(--color-text)] md:text-4xl">
        <Cited metric={metricKey} />
      </div>
      <p className="mt-1 text-sm text-[var(--color-muted)]">{label}</p>
    </div>
  );
}

export function MetricsBand() {
  const filings = getMetric("filings_count");
  const chunks = getMetric("chunks_count");
  const companies = getMetric("companies_count");

  return (
    <section className="px-4 py-16 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          <Stat metricKey="numerical_accuracy_financebench" label="Numerical accuracy, FinanceBench 150Q" />
          <div className="border-t border-[var(--color-border)] pt-4">
            <div className="font-[family-name:var(--font-mono)] text-3xl font-semibold tabular-nums text-[var(--color-text)] md:text-4xl">
              <CountUp target={filings.value} />
            </div>
            <p className="mt-1 text-sm text-[var(--color-muted)]">SEC filings ingested</p>
          </div>
          <div className="border-t border-[var(--color-border)] pt-4">
            <div className="font-[family-name:var(--font-mono)] text-3xl font-semibold tabular-nums text-[var(--color-text)] md:text-4xl">
              <CountUp target={companies.value} />
            </div>
            <p className="mt-1 text-sm text-[var(--color-muted)]">Companies</p>
          </div>
          <div className="border-t border-[var(--color-border)] pt-4">
            <div className="font-[family-name:var(--font-mono)] text-3xl font-semibold tabular-nums text-[var(--color-text)] md:text-4xl">
              <CountUp target={chunks.value} />
            </div>
            <p className="mt-1 text-sm text-[var(--color-muted)]">Chunks embedded</p>
          </div>
        </div>
        <div className="mt-10">
          <TickerMarquee />
        </div>
      </div>
    </section>
  );
}
