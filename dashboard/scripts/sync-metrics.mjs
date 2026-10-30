// Copies eval scores out of evals/results/ (gitignored) into the committed
// dashboard/data/metrics.json. Every value carries its own source so the
// <Cited> component never has to trust a hard-coded number. Keys this script
// does not derive (corpus counts, live latencies, the README-only baseline
// rows) are kept exactly as they are in metrics.json.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..");
const resultsDir = join(repoRoot, "evals", "results");

function loadEval(filename) {
  const p = join(resultsDir, filename);
  if (!existsSync(p)) {
    console.warn(`WARN: ${p} not found (gitignored); metrics.json will keep its last committed value for anything sourced from it.`);
    return null;
  }
  return JSON.parse(readFileSync(p, "utf-8"));
}

const combined = loadEval("eval_combined_1790613849.json");
const financebench = loadEval("latest.json");
const custom = loadEval("eval_custom_1790613849.json");
const bm25Only = loadEval("eval_bm25_only_1790318145.json");
const denseOnly = loadEval("eval_dense_only_1790314408.json");

const pct = (n) => `${(n * 100).toFixed(1)}%`;

const metricsPath = join(__dirname, "..", "data", "metrics.json");
const metrics = JSON.parse(readFileSync(metricsPath, "utf-8"));

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
addEvalMetric("answer_relevancy_combined", combined, "answer_relevancy", "eval_combined_1790613849.json", "Combined 198Q, answer_relevancy (ragas, low, see caveat)");
addEvalMetric("context_precision_combined", combined, "context_precision", "eval_combined_1790613849.json", "Combined 198Q, context_precision (ragas, low, see caveat)");
addEvalMetric("context_recall_combined", combined, "context_recall", "eval_combined_1790613849.json", "Combined 198Q, context_recall (ragas, low, see caveat)");

addEvalMetric("baseline_dense_only_numerical_accuracy", denseOnly, "numerical_accuracy", "eval_dense_only_1790314408.json", "Baseline A (dense only), FinanceBench 150Q, numerical_accuracy");
addEvalMetric("baseline_dense_only_faithfulness", denseOnly, "faithfulness", "eval_dense_only_1790314408.json", "Baseline A (dense only), FinanceBench 150Q, faithfulness");
addEvalMetric("baseline_bm25_only_numerical_accuracy", bm25Only, "numerical_accuracy", "eval_bm25_only_1790318145.json", "Baseline B (BM25 only), FinanceBench 150Q, numerical_accuracy");
addEvalMetric("baseline_bm25_only_faithfulness", bm25Only, "faithfulness", "eval_bm25_only_1790318145.json", "Baseline B (BM25 only), FinanceBench 150Q, faithfulness");

writeFileSync(metricsPath, JSON.stringify(metrics, null, 2) + "\n");
console.log(`Wrote ${Object.keys(metrics).length} metrics to dashboard/data/metrics.json`);
