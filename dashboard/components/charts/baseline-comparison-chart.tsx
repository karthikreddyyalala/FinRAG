"use client";
import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList, Cell } from "recharts";
import { getMetric } from "@/lib/metrics";
import { DataTableFallback } from "@/components/charts/data-table-fallback";

const METRICS = [
  { key: "numerical_accuracy", label: "Numerical accuracy" },
  { key: "faithfulness", label: "Faithfulness" },
] as const;

// One hue (brand accent), three tints — identity carried by direct labels,
// not by hue alone, per taste-skill's single-accent rule.
const TINTS = ["#8fd9bb", "#45c98f", "#1b7a51"];

export function BaselineComparisonChart() {
  const [metric, setMetric] = useState<(typeof METRICS)[number]["key"]>("numerical_accuracy");

  const suffix = metric === "numerical_accuracy" ? "numerical_accuracy" : "faithfulness";
  const dense = getMetric(`baseline_dense_only_${suffix}`);
  const bm25 = getMetric(`baseline_bm25_only_${suffix}`);
  const full =
    metric === "numerical_accuracy"
      ? getMetric("baseline_full_pipeline_numerical_accuracy")
      : getMetric("baseline_full_pipeline_faithfulness");

  const data = [
    { name: "Dense only", value: Math.round(dense.value * 1000) / 10 },
    { name: "BM25 only", value: Math.round(bm25.value * 1000) / 10 },
    { name: "Full pipeline", value: Math.round(full.value * 1000) / 10 },
  ];

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold text-[var(--color-text)]">Retrieval strategy comparison</h3>
        <div className="inline-flex rounded-full border border-[var(--color-border)] p-1">
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => setMetric(m.key)}
              className={`cursor-pointer rounded-full px-3 py-1 text-xs transition-colors duration-200 ${
                metric === m.key ? "bg-[var(--color-grounded)] text-[var(--color-bg)]" : "text-[var(--color-muted)]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-[var(--color-muted)]">FinanceBench 150Q, per README&apos;s baseline comparison table.</p>

      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 32, top: 8, bottom: 8 }}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis
              type="category"
              dataKey="name"
              width={100}
              tick={{ fill: "var(--color-muted)", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 12,
                fontSize: 12,
              }}
              formatter={(v) => [`${v}%`, METRICS.find((m) => m.key === metric)?.label ?? ""]}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={28} isAnimationActive={false}>
              {data.map((_, i) => (
                <Cell key={i} fill={TINTS[i]} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                formatter={(v: React.ReactNode) => `${v}%`}
                style={{ fill: "var(--color-text)", fontSize: 12, fontFamily: "var(--font-mono)" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <DataTableFallback
        caption="Retrieval strategy comparison"
        columns={["Strategy", METRICS.find((m) => m.key === metric)?.label ?? ""]}
        rows={data.map((d) => [d.name, `${d.value}%`])}
      />
    </div>
  );
}
