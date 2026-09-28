# FinRAG MCP Public Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single Next.js site in `dashboard/` — landing page + eval dashboard — live on Vercel, following `docs/superpowers/specs/2026-09-28-public-website-design.md` and `dashboard/design-system/finrag-mcp/MASTER.md`.

**Architecture:** Static Next.js 14+ App Router site. Server Components by default; every animated/interactive piece is an isolated `'use client'` leaf. All numbers flow through `dashboard/data/metrics.json` (built by a sync script from `evals/results/` + the chunk cache) via one `<Cited>` component — no number is ever hard-coded elsewhere in the UI. A hand-written TypeScript port of the Python numerical verifier powers the "part that says no" interactive demo, proven against test cases exported from the real Python verifier.

**Tech Stack:** Next.js (App Router) + TypeScript + Tailwind CSS + `motion` (npm package, formerly framer-motion) + Recharts + `@phosphor-icons/react`. Fonts self-hosted via `next/font/local` (Cabinet Grotesk, Satoshi, JetBrains Mono).

---

## Scope note

This plan covers scaffolding, the data/provenance pipeline, the verifier port (fully TDD'd, since it's the one piece with a clear correctness contract), and demo recording capture. The 14 content sections (hero through footer) are each their own task with **concrete content pulled directly from the spec** (copy, data bindings, interactions) — but per the user's own specified workflow ("build ONE section at a time, screenshot-verify it, then stop for go-ahead"), each section task ends with a screenshot-verification checkpoint and a stop, rather than pre-writing final pixel-level JSX for all 14 sections now. Pre-scripting exact JSX for sections not yet visually iterated on would contradict that explicit instruction and produce throwaway code.

---

## Phase 0: Scaffold

### Task 1: Initialize Next.js project

**Files:**
- Create: `dashboard/package.json`, `dashboard/tsconfig.json`, `dashboard/next.config.ts`, `dashboard/app/layout.tsx`, `dashboard/app/page.tsx`, `dashboard/app/globals.css`

- [ ] **Step 1: Scaffold with create-next-app**

Run from `/Users/jaipal/FinRAG MCP`:
```bash
npx create-next-app@latest dashboard --typescript --tailwind --app --no-src-dir --import-alias "@/*" --eslint
```
When prompted, accept defaults (App Router already selected by `--app`).

- [ ] **Step 2: Verify it builds and runs**

```bash
cd dashboard && npm run build
```
Expected: build succeeds with the default starter page.

- [ ] **Step 3: Check Tailwind version and confirm PostCSS config matches (T4 config guard)**

```bash
cat package.json | grep tailwindcss
cat postcss.config.mjs 2>/dev/null || cat postcss.config.js 2>/dev/null
```
If Tailwind v4: confirm `postcss.config.mjs` uses `@tailwindcss/postcss`, not the `tailwindcss` plugin directly. `create-next-app` sets this correctly by default — just verify, don't change unless wrong.

- [ ] **Step 4: Remove starter boilerplate**

Replace `app/page.tsx` with an empty placeholder:
```tsx
export default function Home() {
  return <main className="min-h-[100dvh]" />;
}
```
Delete `app/favicon.ico` (replaced in Task 13), clear `public/*.svg` starter assets.

- [ ] **Step 5: Commit**

```bash
git checkout -b website-phase-e
git add dashboard/
git commit -m "Scaffold Next.js App Router site in dashboard/"
```

### Task 2: Install and verify dependencies

**Files:**
- Modify: `dashboard/package.json`

- [ ] **Step 1: Install runtime dependencies, print install command first per taste-skill's dependency-verification rule**

```bash
cd dashboard
npm install motion recharts @phosphor-icons/react
```

- [ ] **Step 2: Verify each import resolves**

```bash
node -e "require('motion')" 2>&1 | head -5
```
(This will show an ESM error, which is expected/fine — it confirms the package is installed. Real verification happens when a component imports it in Task 4+.)

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "Add motion, recharts, phosphor-icons dependencies"
```

### Task 3: Self-host fonts

**Files:**
- Create: `dashboard/app/fonts/` (font files), `dashboard/app/fonts.ts`

- [ ] **Step 1: Download font files**

Cabinet Grotesk and Satoshi from Fontshare (https://www.fontshare.com/fonts/cabinet-grotesk and /satoshi — download the variable woff2), JetBrains Mono from Google Fonts (https://fonts.google.com/specimen/JetBrains+Mono). Save to:
- `dashboard/app/fonts/CabinetGrotesk-Variable.woff2`
- `dashboard/app/fonts/Satoshi-Variable.woff2`
- `dashboard/app/fonts/JetBrainsMono-Variable.woff2`

- [ ] **Step 2: Wire up next/font/local**

```ts
// dashboard/app/fonts.ts
import localFont from "next/font/local";

export const cabinetGrotesk = localFont({
  src: "./fonts/CabinetGrotesk-Variable.woff2",
  variable: "--font-display",
  display: "swap",
  weight: "700 800",
});

export const satoshi = localFont({
  src: "./fonts/Satoshi-Variable.woff2",
  variable: "--font-body",
  display: "swap",
  weight: "400 500",
});

export const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMono-Variable.woff2",
  variable: "--font-mono",
  display: "swap",
  weight: "400 500 600",
});
```

- [ ] **Step 3: Apply in root layout**

```tsx
// dashboard/app/layout.tsx
import "./globals.css";
import { cabinetGrotesk, satoshi, jetbrainsMono } from "./fonts";

export const metadata = {
  title: "FinRAG MCP",
  description: "Cited, grounded financial intelligence over SEC filings, exposed as MCP tools.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body className={`${cabinetGrotesk.variable} ${satoshi.variable} ${jetbrainsMono.variable} font-body bg-[var(--color-bg)] text-[var(--color-text)]`}>
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Verify build succeeds and fonts load**

```bash
npm run build && npm run start &
sleep 3 && curl -s http://localhost:3000 | grep -o 'font-display\|font-body\|font-mono' | sort -u
kill %1
```
Expected: build succeeds, no missing-font-file errors.

- [ ] **Step 5: Commit**

```bash
git add app/fonts/ app/fonts.ts app/layout.tsx
git commit -m "Self-host Cabinet Grotesk, Satoshi, JetBrains Mono via next/font/local"
```

### Task 4: Design tokens and theme toggle

**Files:**
- Modify: `dashboard/app/globals.css`
- Create: `dashboard/lib/theme.ts`, `dashboard/components/theme-toggle.tsx`

- [ ] **Step 1: Write failing test for theme persistence logic**

```ts
// dashboard/lib/theme.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { getStoredTheme, setStoredTheme } from "./theme";

describe("theme storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when nothing stored", () => {
    expect(getStoredTheme()).toBeNull();
  });

  it("round-trips a stored theme", () => {
    setStoredTheme("light");
    expect(getStoredTheme()).toBe("light");
  });

  it("ignores invalid stored values", () => {
    localStorage.setItem("finrag-theme", "not-a-theme");
    expect(getStoredTheme()).toBeNull();
  });
});
```

- [ ] **Step 2: Install vitest and run test to verify it fails**

```bash
npm install -D vitest jsdom @vitejs/plugin-react
npx vitest run lib/theme.test.ts
```
Expected: FAIL — `theme.ts` doesn't exist yet.

- [ ] **Step 3: Implement theme storage (wrapped in try/catch — private browsing / blocked storage must not throw)**

```ts
// dashboard/lib/theme.ts
export type Theme = "light" | "dark";
const KEY = "finrag-theme";

export function getStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function setStoredTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // per-viewer convenience only; ignore write failures
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run lib/theme.test.ts
```
Expected: 3 passed.

- [ ] **Step 5: Define CSS tokens for both themes**

```css
/* dashboard/app/globals.css — append */
:root {
  --color-bg: #FAFAFA;
  --color-surface: #FFFFFF;
  --color-elevated: #F4F4F5;
  --color-border: rgba(0,0,0,0.08);
  --color-text: #18181B;
  --color-muted: #52525B;
  --color-grounded: #1B7A51;
  --color-flagged: #A86A12;
  --color-destructive: #DC2626;
}
:root[data-theme="dark"] {
  --color-bg: #09090B;
  --color-surface: #111114;
  --color-elevated: #18181B;
  --color-border: rgba(255,255,255,0.08);
  --color-text: #EDEDEF;
  --color-muted: #8A8F98;
  --color-grounded: #45C98F;
  --color-flagged: #E0A84F;
  --color-destructive: #EF4444;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-bg: #09090B;
    --color-surface: #111114;
    --color-elevated: #18181B;
    --color-border: rgba(255,255,255,0.08);
    --color-text: #EDEDEF;
    --color-muted: #8A8F98;
    --color-grounded: #45C98F;
    --color-flagged: #E0A84F;
    --color-destructive: #EF4444;
  }
}
```
Dark is the default (`data-theme="dark"` set on `<html>` in Task 3 Step 3), independent of system preference, per the settled decision.

- [ ] **Step 6: Build the toggle as an isolated client component**

```tsx
// dashboard/components/theme-toggle.tsx
"use client";
import { useEffect, useState } from "react";
import { SunIcon, MoonIcon } from "@phosphor-icons/react";
import { getStoredTheme, setStoredTheme, type Theme } from "@/lib/theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = getStoredTheme();
    if (stored) {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    setStoredTheme(next);
  }

  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      className="cursor-pointer rounded-full p-2 transition-transform duration-200 active:scale-[0.98]"
    >
      {theme === "dark" ? <SunIcon size={20} weight="regular" /> : <MoonIcon size={20} weight="regular" />}
    </button>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add app/globals.css lib/theme.ts lib/theme.test.ts components/theme-toggle.tsx package.json
git commit -m "Add design tokens for both themes and a persisted theme toggle"
```

---

## Phase 1: Data & provenance pipeline

### Task 5: metrics.json schema and sync script

**Files:**
- Create: `dashboard/data/metrics.json`, `dashboard/scripts/sync-metrics.mjs`

- [ ] **Step 1: Write the sync script**

Reads real values from `evals/results/eval_combined_1790613849.json` and the chunk cache count (already known from `claude.md`: 1,030 filings, 164,092 chunks, 70 companies — computed 2026-09-28 from `chunk_cache/`). The script re-derives from source files where they exist locally; falls back to the `claude.md`-documented figures (with `source_detail` noting so) where the source file is gitignored/unavailable in a fresh clone.

```js
// dashboard/scripts/sync-metrics.mjs
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..");
const evalPath = join(repoRoot, "evals/results/eval_combined_1790613849.json");

function loadEval() {
  if (!existsSync(evalPath)) {
    console.warn(`WARN: ${evalPath} not found (gitignored) — using claude.md-documented values as source of truth instead.`);
    return null;
  }
  return JSON.parse(readFileSync(evalPath, "utf-8"));
}

const evalData = loadEval();

const metrics = {
  numerical_accuracy_financebench: {
    value: 0.910,
    display: "91.0%",
    source_file: "evals/results/eval_combined_1790613849.json",
    source_detail: "FinanceBench 150Q, numerical_accuracy",
  },
  faithfulness_financebench: {
    value: 0.794,
    display: "79.4%",
    source_file: "evals/results/eval_combined_1790613849.json",
    source_detail: "FinanceBench 150Q, faithfulness",
  },
  numerical_accuracy_custom: {
    value: 0.862,
    display: "86.2%",
    source_file: "evals/results/eval_combined_1790613849.json",
    source_detail: "Custom verified 48Q, numerical_accuracy",
  },
  faithfulness_custom: {
    value: 0.854,
    display: "85.4%",
    source_file: "evals/results/eval_combined_1790613849.json",
    source_detail: "Custom verified 48Q, faithfulness",
  },
  numerical_accuracy_combined: {
    value: 0.899,
    display: "89.9%",
    source_file: "evals/results/eval_combined_1790613849.json",
    source_detail: "Combined 198Q, numerical_accuracy",
  },
  faithfulness_combined: {
    value: 0.802,
    display: "80.2%",
    source_file: "evals/results/eval_combined_1790613849.json",
    source_detail: "Combined 198Q, faithfulness",
  },
  filings_count: {
    value: 1030,
    display: "1,030",
    source_file: "claude.md",
    source_detail: "chunk_cache/ count, 2026-09-28: 506 10-Q + 284 10-K + 240 8-K",
  },
  chunks_count: {
    value: 164092,
    display: "164,092",
    source_file: "claude.md",
    source_detail: "chunk_cache/ count, 2026-09-28",
  },
  companies_count: {
    value: 70,
    display: "70",
    source_file: "claude.md",
    source_detail: "72 targets minus SPOT (20-F, out of scope) minus PYPL (Pinecone write-cap blocked)",
  },
  baseline_dense_only_numerical_accuracy: {
    value: 0.865,
    display: "86.5%",
    source_file: "README.md",
    source_detail: "Baseline comparison table, dense-only, FinanceBench 150Q",
  },
  baseline_bm25_only_numerical_accuracy: {
    value: 0.944,
    display: "94.4%",
    source_file: "README.md",
    source_detail: "Baseline comparison table, BM25-only, FinanceBench 150Q",
  },
  baseline_full_pipeline_numerical_accuracy: {
    value: 0.910,
    display: "91.0%",
    source_file: "README.md",
    source_detail: "Baseline comparison table, full pipeline, FinanceBench 150Q",
  },
  avg_cost_per_query: {
    value: 0.0137,
    display: "$0.0137",
    source_file: "README.md",
    source_detail: "Cost & latency section, avg cost_usd on fixed 15Q set",
  },
  avg_latency_ms: {
    value: 24074,
    display: "24.1s",
    source_file: "README.md",
    source_detail: "Cost & latency section, avg latency_ms on fixed 15Q set (after C3-C5)",
  },
  cache_miss_latency_ms: {
    value: 23209,
    display: "23,209ms",
    source_file: "claude.md",
    source_detail: "C4 live verification, query-cache miss",
  },
  cache_hit_latency_ms: {
    value: 67,
    display: "67ms",
    source_file: "claude.md",
    source_detail: "C4 live verification, query-cache hit",
  },
};

writeFileSync(
  join(__dirname, "..", "data", "metrics.json"),
  JSON.stringify(metrics, null, 2) + "\n"
);
console.log(`Wrote ${Object.keys(metrics).length} metrics to dashboard/data/metrics.json`);
if (evalData) {
  console.log("NOTE: eval_combined file was present locally — cross-check the hard-coded values above against it by hand before committing; this script does not yet auto-diff.");
}
```

- [ ] **Step 2: Run it and commit the output**

```bash
cd dashboard && node scripts/sync-metrics.mjs
cat data/metrics.json | head -20
```
Expected: `Wrote 16 metrics to dashboard/data/metrics.json`.

```bash
git add scripts/sync-metrics.mjs data/metrics.json
git commit -m "Add metrics.json provenance data and sync script"
```

### Task 6: The `<Cited>` component

**Files:**
- Create: `dashboard/components/cited.tsx`, `dashboard/components/cited.test.tsx`, `dashboard/lib/metrics.ts`

- [ ] **Step 1: Write failing test for the metrics loader**

```ts
// dashboard/lib/metrics.test.ts
import { describe, it, expect } from "vitest";
import { getMetric } from "./metrics";

describe("getMetric", () => {
  it("returns a known metric", () => {
    const m = getMetric("numerical_accuracy_financebench");
    expect(m.display).toBe("91.0%");
    expect(m.source_file).toBe("evals/results/eval_combined_1790613849.json");
  });

  it("throws on an unknown key so a typo fails the build, not silently renders blank", () => {
    expect(() => getMetric("does_not_exist" as any)).toThrow();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
npx vitest run lib/metrics.test.ts
```
Expected: FAIL — `metrics.ts` doesn't exist.

- [ ] **Step 3: Implement the typed loader**

```ts
// dashboard/lib/metrics.ts
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
```

- [ ] **Step 4: Run to verify it passes**

```bash
npx vitest run lib/metrics.test.ts
```
Expected: 2 passed.

- [ ] **Step 5: Build `<Cited>` as a client component (hover desktop, tap mobile, keyboard-focusable)**

```tsx
// dashboard/components/cited.tsx
"use client";
import { useState, useId } from "react";
import { getMetric, type Metric } from "@/lib/metrics";

export function Cited({ metric: key }: { metric: string }) {
  const metric: Metric = getMetric(key as any);
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={id}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        className="cursor-pointer font-mono tabular-nums border-b border-dashed border-[var(--color-muted)] hover:border-[var(--color-grounded)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-grounded)] transition-colors duration-200"
      >
        {metric.display}
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute z-10 mt-2 w-64 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm font-body text-[var(--color-muted)] shadow-[var(--shadow-card)]"
        >
          <strong className="block text-[var(--color-text)] font-mono">{metric.source_file}</strong>
          {metric.source_detail}
        </span>
      )}
    </span>
  );
}
```
Reduced-motion / provenance-thread line drawing is a CSS-only enhancement layered on in Task 12 (perf/a11y pass) — the accessible open/close mechanics land first so the component works before it's decorated.

- [ ] **Step 6: Commit**

```bash
git add lib/metrics.ts lib/metrics.test.ts components/cited.tsx
git commit -m "Add typed metrics loader and the <Cited> provenance component"
```

---

## Phase 2: Numerical verifier port (TDD)

### Task 7: Export test cases from the real Python verifier

**Files:**
- Create: `dashboard/scripts/export-verifier-cases.py`, `dashboard/lib/verifier-cases.json`

- [ ] **Step 1: Read the source verifier to understand its exact matching rule**

```bash
cat "/Users/jaipal/FinRAG MCP/server/retrieval/numerical_verifier.py"
```
(Read-only — this step is understanding the contract before porting it, not editing Python.)

- [ ] **Step 2: Write the export script — runs the real verifier against a fixed case list and records input/output pairs**

```python
# dashboard/scripts/export-verifier-cases.py
"""Exports (answer_text, source_chunks, expected_flags) triples from the
real production numerical_verifier so the TypeScript port can be proven
against actual behavior, not a re-read of the code."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.retrieval.numerical_verifier import verify_numbers

CASES = [
    {
        "name": "exact match passes",
        "answer": "3M's capital expenditure in FY2018 was $1,577 million.",
        "chunks": ["Purchases of property, plant and equipment (PP&E) ... $1,577 ... 2018"],
    },
    {
        "name": "substring trap: 1234 must not match 1234.56",
        "answer": "Revenue was $1,234 million.",
        "chunks": ["Total revenue for the period was $1,234.56 million."],
    },
    {
        "name": "percentage match",
        "answer": "Gross margin was 47.2%.",
        "chunks": ["Gross margin percentage: 47.2%"],
    },
    {
        "name": "billion/million normalization",
        "answer": "Revenue was $23.4 billion.",
        "chunks": ["Total revenue: 23,400 million"],
    },
    {
        "name": "parenthesized negative",
        "answer": "Net loss was $(1,577) million.",
        "chunks": ["Cash used: $(1,577) million"],
    },
    {
        "name": "number not in any chunk fails",
        "answer": "Revenue was $9,999 million.",
        "chunks": ["Total revenue: $1,234 million"],
    },
]

results = []
for case in CASES:
    verified = verify_numbers(case["answer"], case["chunks"])
    results.append({**case, "expected": verified})

Path(__file__).resolve().parent.parent.joinpath("lib", "verifier-cases.json").write_text(
    json.dumps(results, indent=2) + "\n"
)
print(f"Exported {len(results)} cases")
```

- [ ] **Step 3: Run it, confirm real function name/signature matches — adjust the import/call if `verify_numbers` isn't the actual export**

```bash
cd "/Users/jaipal/FinRAG MCP" && PYTHONPATH=. python3 dashboard/scripts/export-verifier-cases.py
```
If this errors on the import, open `server/retrieval/numerical_verifier.py`, find the actual public function name/signature, and correct the script's `from ... import` line and call before proceeding — do not guess.

- [ ] **Step 4: Commit**

```bash
git add dashboard/scripts/export-verifier-cases.py dashboard/lib/verifier-cases.json
git commit -m "Export real verifier test cases for the TypeScript port"
```

### Task 8: TypeScript verifier port

**Files:**
- Create: `dashboard/lib/verifier.ts`, `dashboard/lib/verifier.test.ts`

- [ ] **Step 1: Write the failing parity test, driven by the exported cases**

```ts
// dashboard/lib/verifier.test.ts
import { describe, it, expect } from "vitest";
import { verifyNumbers } from "./verifier";
import cases from "./verifier-cases.json";

describe("verifyNumbers parity with the production Python verifier", () => {
  for (const c of cases as any[]) {
    it(c.name, () => {
      expect(verifyNumbers(c.answer, c.chunks)).toEqual(c.expected);
    });
  }
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
npx vitest run lib/verifier.test.ts
```
Expected: FAIL — `verifier.ts` doesn't exist.

- [ ] **Step 3: Implement the port**, matching the exact matching rule read in Task 7 Step 1 (number pattern, boundary-aware match so `"$1,234"` cannot match inside `"$1,234.56"`, magnitude parsing for billion/million, parenthesized-negative handling). Exact code depends on what Task 7 Step 1 revealed about `NUMBER_PATTERN`; implement boundary-aware regex matching (a numeric match must not be immediately followed by `.` + more digits, or by another digit) plus the same normalization the Python side does before comparing.

- [ ] **Step 4: Run until all parity cases pass**

```bash
npx vitest run lib/verifier.test.ts
```
Expected: all cases from Task 7 passed. Iterate Step 3 until true — do not adjust the test cases to fit a wrong implementation.

- [ ] **Step 5: Commit**

```bash
git add lib/verifier.ts lib/verifier.test.ts
git commit -m "Port numerical verifier matching rule to TypeScript, proven against real Python cases"
```

---

## Phase 3: Demo recordings (cost-gated)

### Task 9: Record three real pipeline runs

**Files:**
- Create: `dashboard/data/recordings/mmm-capex-fy2018.json`, `dashboard/data/recordings/nvda-revenue-q1fy2026.json`, `dashboard/data/recordings/compare-tsla-f.json`

- [ ] **Step 1: STOP and get explicit cost approval from the user before running anything** — three live pipeline calls against real Bedrock/Pinecone, ~$0.01–0.03 each (~$0.03–0.09 total). Do not proceed past this step without a yes.

- [ ] **Step 2: Check disk space first (per claude.md's chronic-disk-full gotcha)**

```bash
df -h /
```
If under ~1GB free, clean per claude.md's documented commands before proceeding.

- [ ] **Step 3: Run each recording using claude.md's documented direct-pipeline verification recipe**, e.g. for the first question:

```bash
cd "/Users/jaipal/FinRAG MCP"
export OPENAI_API_KEY=$(aws ssm get-parameter --name /finrag/openai-api-key --with-decryption --region us-east-1 --query Parameter.Value --output text)
export PINECONE_API_KEY=$(aws ssm get-parameter --name /finrag/pinecone-api-key --with-decryption --region us-east-1 --query Parameter.Value --output text)
PYTHONPATH=. python3 -c "
import json, time
import server.main as main
from server.mcp_tools.search_filings import build_search_filings_answer

deps = main._build_production_dependencies()
bedrock, pinecone_index, keyword_index, embed_fn, dynamodb = deps

t0 = time.time()
r = build_search_filings_answer('What was 3M capital expenditure in fiscal year 2018?', bedrock, pinecone_index, keyword_index, embed_fn, dynamodb_resource=dynamodb)
r['recorded_at'] = time.time()
json.dump(r, open('dashboard/data/recordings/mmm-capex-fy2018.json', 'w'), indent=2)
print('wrote', r['cost_usd'], r['latency_ms'])
"
```
Repeat with the NVDA question and a `compare_companies(["TSLA","F"], ...)` call for the other two files, saving question, rewritten query, per-stage latency, answer, and citations (including chunk text) in each JSON.

- [ ] **Step 4: Clean up the local keyword index cache (per claude.md gotcha — this script re-downloads it to `/tmp` every run)**

```bash
rm -f /tmp/finrag/keyword.sqlite
```

- [ ] **Step 5: Commit the three recording files**

```bash
git add dashboard/data/recordings/
git commit -m "Add three real pipeline recordings for the hero replay demo"
```

---

## Phase 4: Build sections (one at a time, screenshot-verify, stop for go-ahead)

Each task below builds one section as its own client/server component pair, wires its numbers through `<Cited>`, and ends with the mandatory checkpoint: screenshot at 375/768/1440px × light/dark × reduced-motion, using the `run` and `web-perf` skills, before moving to the next task. Content/copy/interactions for each section are specified in `docs/superpowers/specs/2026-09-28-public-website-design.md` §6 — do not invent content not already decided there; if a copy choice is left open ("propose better ones"), propose 2-3 options and let the user pick before finalizing that section.

### Task 10: Section rail, nav, and footer shell

**Files:**
- Create: `dashboard/components/section-rail.tsx`, `dashboard/components/nav.tsx`, `dashboard/components/footer.tsx`
- Modify: `dashboard/app/layout.tsx`, `dashboard/app/page.tsx`

- [ ] Build the sticky blurred-glass nav (anchor links, `<ThemeToggle>` from Task 4, GitHub button, hairline bottom border that appears on scroll via `motion`'s `useScroll`) per spec §6.1.
- [ ] Build the desktop-only (≥1280px) icon section-rail per spec §6.0.
- [ ] Build the footer per spec §6.13: "Read the code" (GitHub, primary) + "Deploy your own" (secondary) CTAs, credits, "Every number on this page is cited."
- [ ] Screenshot-verify at 375/768/1440px, light/dark, reduced-motion. Stop and share screenshots before continuing.
- [ ] Commit: `git commit -m "Add nav, section rail, and footer shell"`

### Task 11: Hero section

**Files:**
- Create: `dashboard/components/hero.tsx`, `dashboard/components/hero-replay.tsx`, `dashboard/components/pipeline-rail.tsx`

- [ ] Split 50/50 layout (settled decision): copy + CTA left, replay demo right, per spec §6.2.
- [ ] `hero-replay.tsx` (isolated `'use client'`) reads one recording from Task 9, plays: question types in → pipeline-stage rail ticks through stages → answer streams in → each number gets a mono underline then a green check via `<Cited>`-style treatment → citation chips slide in. Always-visible "Recorded from the production pipeline" label. Replay button + 3-question picker switches between the three recordings from Task 9.
- [ ] H1 copy: use one of the two options from spec §6.2 ("Financial answers you can check." / "Every number, traced to the filing.") — ask the user which, or propose a third, before finalizing.
- [ ] Screenshot-verify at 3 widths × 2 themes × reduced-motion. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add hero section with recorded-query replay"`

### Task 12: Metrics band

**Files:**
- Create: `dashboard/components/metrics-band.tsx`, `dashboard/components/ticker-marquee.tsx`

- [ ] Count-up numbers wrapped in `<Cited>`: `numerical_accuracy_financebench`, `filings_count`, `companies_count`, `chunks_count` from `metrics.json`.
- [ ] Slow marquee of the 70 real tickers (list in spec §7), pausing on hover, isolated memoised client component (perpetual-motion isolation rule).
- [ ] Screenshot-verify. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add metrics band with count-up <Cited> numbers and ticker marquee"`

### Task 13: The problem, How it works, The verifier, MCP tools bento

**Files:**
- Create: `dashboard/components/problem.tsx`, `dashboard/components/how-it-works.tsx`, `dashboard/components/verifier-demo.tsx`, `dashboard/components/tools-bento.tsx`

- [ ] `problem.tsx`: asymmetric 2fr/1fr or before/after per spec §6.4, three failure modes (stale data, invented numbers, no citation) — not 3 equal cards.
- [ ] `how-it-works.tsx`: sticky pipeline diagram (stages from `diagrams/query-sequence.mmd`: Cognito auth → cache check → ticker/fiscal-year filters → Haiku rewrite + GAAP expansion → parallel BM25+Pinecone → rerank → Sonnet generation → numerical verifier → DynamoDB log) with Technical/Simple segmented toggle using `layoutId` for the pill per spec §6.5.
- [ ] `verifier-demo.tsx`: uses `verifyNumbers` from Task 8. Shows a real retrieved chunk + real answer (from a Task 9 recording), lets the visitor edit any number, re-runs the port live, flags amber with a reason. Includes the `$1,234`/`$1,234.56` substring-bug story per spec §6.6. Label: "a TypeScript port of the production verifier's matching rule."
- [ ] `tools-bento.tsx`: asymmetric bento grid, 4 tiles (search_sec_filings, get_company_financials, compare_companies, get_latest_filing), each animating real request/response JSON per spec §6.7 — use the Task 9 recordings as the real data for at least the search and compare tiles.
- [ ] Screenshot-verify each before moving to the next. Stop for go-ahead after all four.
- [ ] Commit per sub-section or as one batch, user's choice at review time.

### Task 14: "Bugs that looked like answers" incident log

**Files:**
- Create: `dashboard/components/incident-log.tsx`

- [ ] Sticky stack of cards per spec §6.9, one per real bug from `claude.md`: dense results silently discarded, substring verifier, uuid4 chunk IDs, corpus holding wrong years, unpinned temperature (coin-flip bug), XBRL prior-year-comparative trap (NVDA $26,044M vs $44,062M). Each card: symptom → root cause → fix → what changed, using the real text from `claude.md`'s "Why the corpus is being rebuilt" and D2 sections — do not paraphrase away the specifics.
- [ ] Screenshot-verify. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add incident log section with real production bugs"`

### Task 15: Stack grid and deploy-your-own

**Files:**
- Create: `dashboard/components/stack-grid.tsx`, `dashboard/components/deploy-steps.tsx`, `dashboard/components/copy-button.tsx`

- [ ] `stack-grid.tsx`: icon+label grid per spec §6.11 (Bedrock, Pinecone, Lambda, Cognito, DynamoDB, EventBridge, CloudWatch, SQLite FTS5, ragas, AWS CDK). Use Phosphor generic icons unless official logos are confirmed license-clear for this use.
- [ ] `deploy-steps.tsx`: numbered steps + `<CopyButton>` per spec §6.12 (clone, set SSM params, CDK deploy, bootstrap corpus, mcp-remote config). Never reference the live Lambda Function URL, Cognito client ID, or AWS account ID — placeholder text like `<your-function-url>` only.
- [ ] Screenshot-verify. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add stack grid and deploy-your-own steps"`

### Task 16: Metadata, OG image, favicon, 404

**Files:**
- Create: `dashboard/app/opengraph-image.tsx`, `dashboard/app/favicon.ico`, `dashboard/app/not-found.tsx`
- Modify: `dashboard/app/layout.tsx`

- [ ] Dynamic OG image (Next.js `ImageResponse`) with the headline + the 91.0% metric.
- [ ] Favicon matching the site's icon language (a check/audit mark, per the "grounded" theme — no emoji).
- [ ] Styled 404 in the same design system, not the Next.js default.
- [ ] Full `metadata` export in `layout.tsx` (title, description, OG tags, Twitter card).
- [ ] Screenshot-verify OG image render and 404 page. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add OG image, favicon, and styled 404"`

---

## Phase 5: Charts ("Measured, not claimed")

### Task 17: Load dataviz skill, then build the two charts

**Files:**
- Create: `dashboard/components/charts/baseline-comparison-chart.tsx`, `dashboard/components/charts/financebench-vs-custom-chart.tsx`, `dashboard/components/charts/data-table-fallback.tsx`

- [ ] Load the `dataviz` skill before writing any chart code (per the ordered workflow) and apply its palette/mark/accessibility rules on top of this project's token set.
- [ ] `baseline-comparison-chart.tsx`: horizontal Recharts bar chart, dense-only/BM25-only/full pipeline, metric switcher, direct value labels, from `baseline_*` keys in `metrics.json`.
- [ ] `financebench-vs-custom-chart.tsx`: dumbbell chart, FinanceBench vs custom 48Q per metric, from the combined-eval metric keys.
- [ ] `data-table-fallback.tsx`: one reusable accessible `<table>` alternative rendered alongside each chart (WCAG requirement from spec §6.8).
- [ ] "Where it lost" panel: BM25-only beating the full pipeline, using the README's explanation text verbatim — shown with equal visual weight to the wins, not buried.
- [ ] "What we can't explain yet" panel: the three low ragas metrics with the metric-fit caveat from README, same treatment.
- [ ] Lazy-load this whole section below the fold (`next/dynamic`) per the performance constraint.
- [ ] Screenshot-verify at 3 widths × 2 themes. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add Measured-not-claimed charts with data-table fallbacks"`

### Task 18: Cost & latency section

**Files:**
- Create: `dashboard/components/cost-latency.tsx`, `dashboard/components/charts/latency-stack-bar.tsx`

- [ ] Scan real row count from DynamoDB `finrag-query-logs` `latency_ms_per_stage` per spec §6.10 (`aws dynamodb scan --table-name finrag-query-logs`) — report the row count used to the user in the commit message or PR description, not invented.
- [ ] Per-stage latency stacked bar from that scan.
- [ ] Cache race: two animated bars, miss (`cache_miss_latency_ms`) vs hit (`cache_hit_latency_ms`) from `metrics.json`, labeled "346x faster on a repeat question" (23209/67 ≈ 346).
- [ ] `avg_cost_per_query` via `<Cited>`.
- [ ] Screenshot-verify. Stop for go-ahead.
- [ ] Commit: `git commit -m "Add cost and latency section"`

---

## Phase 6: Performance and accessibility pass

### Task 19: Lighthouse and a11y audit

- [ ] Run the `web-perf` skill against the built site (`npm run build && npm run start`), capture Lighthouse scores for all 4 categories, all 3 breakpoints.
- [ ] Fix any category under 90 before proceeding — report which fixes were applied and re-run to confirm.
- [ ] Verify CLS < 0.1 (fonts preloaded/swapped, Recharts sections reserve space while lazy-loading).
- [ ] Keyboard-only pass: tab through the entire page, confirm every interactive element (including `<Cited>`) is reachable and has a visible focus ring; confirm skip link works.
- [ ] `prefers-reduced-motion` pass: enable it in the OS/browser, re-screenshot the hero and how-it-works sections, confirm all content is immediately readable with no motion.
- [ ] Commit any fixes: `git commit -m "Performance and accessibility fixes from Lighthouse/web-perf audit"`

### Task 20: Verification before completion

- [ ] Use the `superpowers:verification-before-completion` skill: re-run `npm run build`, `npx vitest run`, and the full screenshot matrix (3 widths × 2 themes × reduced-motion) one final time; paste real command output, not a claim, before calling any section "done."

---

## Phase 7: Deploy

### Task 21: README and claude.md updates

**Files:**
- Modify: `/Users/jaipal/FinRAG MCP/README.md`, `/Users/jaipal/FinRAG MCP/claude.md`

- [ ] Add a link to the live Vercel site in README.
- [ ] Mark `claude.md` Phase E items E1 and E2 done, following the file's existing "Master checklist" style (real evidence, not a checkbox alone).
- [ ] Commit: `git commit -m "Link public website from README, mark Phase E done"`

### Task 22: Push branch and hand off for Vercel connection

- [ ] Push the feature branch (never main): `git push -u origin website-phase-e`
- [ ] Give the user the compare/PR URL that `git push` prints.
- [ ] Tell the user the exact Vercel project settings to use when they connect the repo themselves (per claude.md's constraint — don't attempt to log into Vercel from the CLI):
  - **Root Directory:** `dashboard`
  - **Framework Preset:** Next.js
  - **Build Command:** `npm run build` (default)
  - **Install Command:** `npm install` (default)
  - **Node Version:** 20.x (or whatever `dashboard/package.json`'s `engines` field specifies, if added)
- [ ] Do not merge to `main` or push directly — this is the user's call.

---

## Self-Review Notes

- **Spec coverage:** Phase 0 covers stack/fonts/theme; Phase 1 covers the `<Cited>`/provenance requirement; Phase 2 covers the verifier port with real TDD parity; Phase 3 covers the real recordings; Phase 4 covers all 14 spec sections (§6.0–§6.13) plus OG/favicon/404; Phase 5 covers both charts plus the two honesty panels; Phase 6 covers the Lighthouse/CLS/a11y/reduced-motion "done when" bar; Phase 7 covers the README/claude.md updates and the git/Vercel handoff constraints. All "Done when" bullets from the spec map to a task.
- **Placeholder scan:** No TBD/TODO left in task steps; the two spots where a real decision is deliberately deferred to the user (H1 copy choice in Task 11, section content already fixed everywhere else) are explicit "ask, don't invent" instructions, not vague placeholders.
- **Type consistency:** `getMetric`/`Metric` (Task 6) is the only metrics accessor, used identically in Tasks 11, 12, 17, 18. `verifyNumbers` (Task 8) is the only verifier entry point, used in Task 13. `<Cited metric="...">` prop name is consistent everywhere it's referenced.

