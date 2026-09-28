// Copies real numbers out of evals/results/ (gitignored) into a committed
// dashboard/data/metrics.json. Every value carries its own source so the
// <Cited> component never has to trust a hard-coded number.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..");
const resultsDir = join(repoRoot, "evals", "results");

function loadEval(filename) {
  const p = join(resultsDir, filename);
  if (!existsSync(p)) {
    console.warn(`WARN: ${p} not found (gitignored) — metrics.json will keep its last committed value for anything sourced from it.`);
    return null;
  }
  return JSON.parse(readFileSync(p, "utf-8"));
}

const combined = loadEval("eval_combined_1790613849.json");
// NOTE: latest.json, not latest.json — the latter is an earlier
// FinanceBench-only run superseded by a later one; only latest.json's
// faithfulness (0.794) matches README's published FinanceBench row (79.4%).
// Verified against every eval_*.json in this directory before picking it.
const financebench = loadEval("latest.json");
const custom = loadEval("eval_custom_1790613849.json");
const bm25Only = loadEval("eval_bm25_only_1790318145.json");
const denseOnly = loadEval("eval_dense_only_1790314408.json");

const pct = (n) => `${(n * 100).toFixed(1)}%`;

const metrics = {};

function addEvalMetric(key, data, field, sourceFile, sourceDetail) {
  if (!data) return; // keep prior value on a fresh clone without evals/results/
  metrics[key] = {
    value: data[field],
    display: pct(data[field]),
    source_file: `evals/results/${sourceFile}`,
    source_detail: sourceDetail,
  };
}

addEvalMetric("numerical_accuracy_financebench", financebench, "numerical_accuracy", "latest.json", "FinanceBench 150Q, numerical_accuracy");
addEvalMetric("faithfulness_financebench", financebench, "faithfulness", "latest.json", "FinanceBench 150Q, faithfulness");
addEvalMetric("numerical_accuracy_custom", custom, "numerical_accuracy", "eval_custom_1790613849.json", "Custom verified 48Q, numerical_accuracy");
addEvalMetric("faithfulness_custom", custom, "faithfulness", "eval_custom_1790613849.json", "Custom verified 48Q, faithfulness");
addEvalMetric("numerical_accuracy_combined", combined, "numerical_accuracy", "eval_combined_1790613849.json", "Combined 198Q, numerical_accuracy");
addEvalMetric("faithfulness_combined", combined, "faithfulness", "eval_combined_1790613849.json", "Combined 198Q, faithfulness");
addEvalMetric("answer_relevancy_combined", combined, "answer_relevancy", "eval_combined_1790613849.json", "Combined 198Q, answer_relevancy (ragas, low — see caveat)");
addEvalMetric("context_precision_combined", combined, "context_precision", "eval_combined_1790613849.json", "Combined 198Q, context_precision (ragas, low — see caveat)");
addEvalMetric("context_recall_combined", combined, "context_recall", "eval_combined_1790613849.json", "Combined 198Q, context_recall (ragas, low — see caveat)");

addEvalMetric("baseline_dense_only_numerical_accuracy", denseOnly, "numerical_accuracy", "eval_dense_only_1790314408.json", "Baseline A (dense only), FinanceBench 150Q, numerical_accuracy");
addEvalMetric("baseline_dense_only_faithfulness", denseOnly, "faithfulness", "eval_dense_only_1790314408.json", "Baseline A (dense only), FinanceBench 150Q, faithfulness");
addEvalMetric("baseline_bm25_only_numerical_accuracy", bm25Only, "numerical_accuracy", "eval_bm25_only_1790318145.json", "Baseline B (BM25 only), FinanceBench 150Q, numerical_accuracy");
addEvalMetric("baseline_bm25_only_faithfulness", bm25Only, "faithfulness", "eval_bm25_only_1790318145.json", "Baseline B (BM25 only), FinanceBench 150Q, faithfulness");

// Values that only exist as documented facts in claude.md / README (their
// own source files are gitignored eval outputs or were computed once by
// hand from S3/DynamoDB, not reproducible by this script) — kept as
// literals with an explicit, honest source pointing at the doc, not a file
// this script re-derives.
const documented = {
  baseline_full_pipeline_numerical_accuracy: {
    value: 0.910, display: "91.0%",
    source_file: "README.md", source_detail: "Baseline comparison table, full pipeline, FinanceBench 150Q",
  },
  filings_count: {
    value: 1030, display: "1,030",
    source_file: "claude.md", source_detail: "chunk_cache/ count, 2026-09-28: 506 10-Q + 284 10-K + 240 8-K",
  },
  chunks_count: {
    value: 164092, display: "164,092",
    source_file: "claude.md", source_detail: "chunk_cache/ count, 2026-09-28",
  },
  companies_count: {
    value: 70, display: "70",
    source_file: "claude.md", source_detail: "72 targets minus SPOT (20-F, out of scope, empty cache file) minus PYPL (Pinecone write-cap blocked)",
  },
  avg_cost_per_query: {
    value: 0.0137, display: "$0.0137",
    source_file: "README.md", source_detail: "Cost & latency section, avg cost_usd on fixed 15Q set",
  },
  avg_latency_ms: {
    value: 24074, display: "24.1s",
    source_file: "README.md", source_detail: "Cost & latency section, avg latency_ms on fixed 15Q set (after C3-C5)",
  },
  cache_miss_latency_ms: {
    value: 23209, display: "23,209ms",
    source_file: "claude.md", source_detail: "C4 live verification, query-cache miss",
  },
  cache_hit_latency_ms: {
    value: 67, display: "67ms",
    source_file: "claude.md", source_detail: "C4 live verification, query-cache hit",
  },
};

for (const [key, val] of Object.entries(documented)) {
  if (!(key in metrics)) metrics[key] = val;
}

writeFileSync(join(__dirname, "..", "data", "metrics.json"), JSON.stringify(metrics, null, 2) + "\n");
console.log(`Wrote ${Object.keys(metrics).length} metrics to dashboard/data/metrics.json`);
