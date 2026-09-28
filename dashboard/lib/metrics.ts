import metricsData from "@/data/metrics.json";

export type Metric = {
  value: number;
  display: string;
  source_file: string;
  source_detail: string;
};

const metrics = metricsData as Record<string, Metric>;

export function getMetric(key: keyof typeof metrics): Metric {
  const m = metrics[key];
  if (!m) throw new Error(`Unknown metric key: ${String(key)}`);
  return m;
}
