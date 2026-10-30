import mmm from "@/data/recordings/mmm-capex-fy2018.json";
import nvda from "@/data/recordings/nvda-revenue-q1fy2027.json";
import compareTslaF from "@/data/recordings/compare-tsla-f.json";

export type Recording = {
  id: string;
  question: string;
  tool: string;
  tool_ms: number;
  passages: { id: string; citation: string; ticker: string; form: string; filed: string; excerpt: string }[];
  answer: string;
  model: string;
  verify: { grounded: string[]; not_found: string[] };
};

export const RECORDINGS: Recording[] = [mmm, nvda, compareTslaF];

/** Distinct citation labels, in order, without the surrounding brackets. */
export function citationLabels(r: Recording): string[] {
  return Array.from(new Set(r.passages.map((p) => p.citation.replace(/^\[|\]$/g, ""))));
}
