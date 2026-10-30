import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import corpus from "@/data/corpus.json";
import live from "@/data/live/live-check.json";
import { getMetric } from "./metrics";

const RECORDINGS_DIR = join(process.cwd(), "data/recordings");

describe("corpus.json", () => {
  it("has positive integer counts and by_form sums to filings", () => {
    for (const n of [corpus.companies, corpus.filings, corpus.chunks]) {
      expect(Number.isInteger(n) && n > 0).toBe(true);
    }
    const sum = Object.values(corpus.by_form as Record<string, number>).reduce((a, b) => a + b, 0);
    expect(sum).toBe(corpus.filings);
  });

  it("matches the counts shown through metrics.json", () => {
    expect(getMetric("companies_count").value).toBe(corpus.companies);
    expect(getMetric("filings_count").value).toBe(corpus.filings);
    expect(getMetric("chunks_count").value).toBe(corpus.chunks);
  });
});

describe("live-check.json", () => {
  it("lists exactly 6 tools", () => {
    expect(live.tools).toHaveLength(6);
    expect(Object.keys(live.samples).sort()).toEqual([...live.tools].sort());
  });
});

describe("recordings", () => {
  const files = readdirSync(RECORDINGS_DIR).filter((f) => f.endsWith(".json"));

  it("has three recordings", () => {
    expect(files).toHaveLength(3);
  });

  it.each(files)("%s has a model, an answer, passages and a verify result", (f) => {
    const r = JSON.parse(readFileSync(join(RECORDINGS_DIR, f), "utf8"));
    expect(r.model).toBeTruthy();
    expect(r.answer).toBeTruthy();
    expect(r.passages.length).toBeGreaterThan(0);
    expect(Array.isArray(r.verify.grounded)).toBe(true);
    expect(Array.isArray(r.verify.not_found)).toBe(true);
    expect(r.tool_ms).toBeGreaterThan(0);
  });
});
