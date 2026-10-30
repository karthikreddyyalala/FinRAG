import live from "@/data/live/live-check.json";

type Passage = { id: string; citation: string; text: string };
const S = live.samples;

/** Table text with empty and repeated cells dropped, cut to a short window around `anchor`. */
function excerpt(text: string, anchor?: string, max = 190): string {
  const cells = text.replace(/ /g, " ").split(/\s*\|\s*|\n/).map((c) => c.trim());
  const kept = cells.filter((c, i) => c && c !== cells.slice(0, i).filter(Boolean).at(-1));
  const clean = kept.join(" | ");
  const at = anchor ? clean.indexOf(anchor) : -1;
  const start = at > 40 ? at - 40 : 0;
  return (start ? "... " : "") + clean.slice(start, start + max).trim() + " ...";
}

function pick(passages: Passage[], id: string, anchor?: string) {
  const p = passages.find((x) => x.id.startsWith(id)) ?? passages[0];
  return { citation: p.citation, text: excerpt(p.text, anchor) };
}

const search = S.search_sec_filings.passages as Passage[];
type Figure = {
  label: string; display: string; citation: string; id: string;
  period: { fiscal_year: number; fiscal_period: string; end: string };
  source: { url: string };
};
const financials = S.get_company_financials.result.results as Figure[];
const compare = S.compare_companies.result.results as Record<string, { results: Figure[] }>;

/** The fields a client reads from one figure. */
function figure(f: Figure) {
  return { label: f.label, display: f.display, period: f.period, citation: f.citation, id: f.id };
}
const latest = S.get_latest_filing.result;
const covered = S.list_covered_companies.result;
const verify = S.verify_figures;

const TOOLS = [
  {
    name: "search_sec_filings",
    description: "Free-text search over every filing. Optional ticker and fiscal year filters.",
    request: { question: "3M capital expenditure", ticker: "MMM", fiscal_year: 2018 },
    response: {
      passages: [pick(search, "dd73d7", "Purchases of property"), `... ${search.length - 1} more`],
    },
    span: "md:col-span-2",
  },
  {
    name: "get_company_financials",
    description: "Exact reported figures for any US-listed company, read from the XBRL data in its filings, with period, filing link and citation. Q4 is labelled when derived.",
    request: S.get_company_financials.arguments,
    response: { results: financials.map(figure) },
    span: "md:col-span-2",
  },
  {
    name: "compare_companies",
    description: "The same figures for two to five companies, side by side.",
    request: S.compare_companies.arguments,
    response: {
      results: Object.fromEntries(
        Object.entries(compare).map(([t, c]) => [t, c.results.map((f) => `${f.display} ${f.citation}`)]),
      ),
    },
    span: "",
  },
  {
    name: "get_latest_filing",
    description: "Any company SEC lists, any form (10-K by default), looked up live from EDGAR, with a flag for whether it is already in the corpus.",
    request: S.get_latest_filing.arguments,
    response: { filing: latest.filing, in_corpus: latest.in_corpus },
    span: "md:col-span-2",
  },
  {
    name: "list_covered_companies",
    description: "Every ticker with first and last filing date per form. Call it to see exact years.",
    request: S.list_covered_companies.arguments,
    response: {
      total_filings: covered.total_filings,
      companies: [covered.companies[0], `... ${covered.companies.length - 1} more`],
    },
    span: "",
  },
  {
    name: "verify_figures",
    description: "Send your draft answer and the passage and figure ids. Each dollar amount, percentage and comma-grouped number comes back grounded or not_found; against a figure, units convert.",
    request: { ...verify.arguments, passage_ids: [...verify.arguments.passage_ids.slice(0, 2), "..."] },
    response: { grounded: verify.result.grounded, not_found: verify.result.not_found, checked_against: verify.result.checked_against },
    span: "",
  },
];

export function ToolsBento() {
  return (
    <section id="tools" className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Six tools. Figures and evidence in, your model writes.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Requests and responses below are real calls to the live server, with passage text shortened.
          Figures work for any US-listed company; passage search covers 71.
        </p>
        <div className="mt-8 grid gap-6 md:grid-flow-dense md:grid-cols-3">
          {TOOLS.map((tool) => (
            <div
              key={tool.name}
              className={`min-w-0 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ${tool.span}`}
            >
              <h3 className="font-[family-name:var(--font-mono)] text-sm font-semibold text-[var(--color-grounded)]">
                {tool.name}
              </h3>
              <p className="mt-2 text-sm text-[var(--color-muted)]">{tool.description}</p>
              <pre className="mt-4 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-[var(--color-elevated)] p-3 font-[family-name:var(--font-mono)] text-[11px] leading-relaxed text-[var(--color-text)]">
                {JSON.stringify(tool.request, null, 2)}
              </pre>
              <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-[var(--color-elevated)] p-3 font-[family-name:var(--font-mono)] text-[11px] leading-relaxed text-[var(--color-grounded)]">
                {JSON.stringify(tool.response, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
