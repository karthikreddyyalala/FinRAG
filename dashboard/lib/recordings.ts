import mmm from "@/data/recordings/mmm-capex-fy2018.json";
import nvda from "@/data/recordings/nvda-revenue-q1fy2026.json";
import compareTslaF from "@/data/recordings/compare-tsla-f.json";

export type Citation = {
  ticker: string;
  filing_type: string;
  period: string;
  page: number | null;
  text: string;
};

export type Recording = {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  latency_ms: number;
  cost_usd: number;
};

function fromSearchResult(id: string, question: string, raw: typeof mmm): Recording {
  return {
    id,
    question,
    answer: raw.answer,
    citations: raw.citations as Citation[],
    latency_ms: raw.latency_ms,
    cost_usd: raw.cost_usd,
  };
}

export const RECORDINGS: Recording[] = [
  fromSearchResult("mmm-capex-fy2018", "What was 3M's capital expenditure in fiscal year 2018?", mmm),
  fromSearchResult("nvda-revenue-q1fy2026", "What was Nvidia total revenue in Q1 2026?", nvda),
  {
    id: "compare-tsla-f",
    question: "Compare Tesla and Ford revenue in 2024",
    answer: compareTslaF.companies.map((c: { ticker: string; answer?: string; error?: string }) => `${c.ticker}: ${c.answer ?? c.error}`).join("\n"),
    citations: compareTslaF.companies.flatMap(
      (c: { citations?: Citation[] }) => c.citations ?? []
    ),
    latency_ms: compareTslaF.latency_ms,
    cost_usd: compareTslaF.cost_usd,
  },
];
