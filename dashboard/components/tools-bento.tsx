import { RECORDINGS } from "@/lib/recordings";

const TOOLS = [
  {
    name: "search_sec_filings",
    description: "Full four-stage pipeline over free-text financial questions.",
    request: { query: RECORDINGS[0].question },
    response: { answer: RECORDINGS[0].answer.slice(0, 140) + "…", citations: RECORDINGS[0].citations.length },
    span: "md:col-span-2",
  },
  {
    name: "get_company_financials",
    description: "Targeted lookup for a known ticker, metric, and period. Routed to Haiku — ~3x cheaper on a spot-check.",
    request: { ticker: "MMM", metric: "capital_expenditure", period: "FY2018" },
    response: { answer: "$1,577 million", citation: "MMM 10-K 2019-02-07" },
    span: "",
  },
  {
    name: "compare_companies",
    description: "Multi-hop: one lookup per ticker, merged into a side-by-side answer.",
    request: { tickers: ["TSLA", "F"], metric: "revenue", period: "2024" },
    response: {
      TSLA: "$97.69 billion",
      F: "$167,218 million",
    },
    span: "",
  },
  {
    name: "get_latest_filing",
    description: "Metadata lookup + a short summary, no full RAG pipeline.",
    request: { ticker: "AAPL", filing_type: "10-Q" },
    response: { filing_date: "most recent on EDGAR", summary: "3-sentence executive summary" },
    span: "md:col-span-2",
  },
] as const;

export function ToolsBento() {
  return (
    <section id="tools" className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Four tools, one grounded answer each.
        </h2>
        <div className="mt-8 grid gap-6 md:grid-cols-3">
          {TOOLS.map((tool) => (
            <div
              key={tool.name}
              className={`rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ${tool.span}`}
            >
              <h3 className="font-[family-name:var(--font-mono)] text-sm font-semibold text-[var(--color-grounded)]">
                {tool.name}
              </h3>
              <p className="mt-2 text-sm text-[var(--color-muted)]">{tool.description}</p>
              <pre className="mt-4 overflow-auto rounded-xl bg-[var(--color-elevated)] p-3 font-[family-name:var(--font-mono)] text-[11px] leading-relaxed text-[var(--color-text)]">
                {JSON.stringify(tool.request, null, 2)}
              </pre>
              <pre className="mt-2 overflow-auto rounded-xl bg-[var(--color-elevated)] p-3 font-[family-name:var(--font-mono)] text-[11px] leading-relaxed text-[var(--color-grounded)]">
                {JSON.stringify(tool.response, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
