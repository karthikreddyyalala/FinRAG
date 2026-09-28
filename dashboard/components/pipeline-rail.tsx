"use client";
import { motion } from "motion/react";

export const PIPELINE_STAGES = [
  "Cognito auth",
  "Cache check",
  "Ticker + fiscal-year filters",
  "Haiku rewrite + GAAP expansion",
  "BM25 + Pinecone",
  "Rerank",
  "Sonnet generation",
  "Numerical verifier",
] as const;

export function PipelineRail({ activeIndex }: { activeIndex: number }) {
  return (
    <ol className="flex flex-wrap gap-2" aria-label="Pipeline stages">
      {PIPELINE_STAGES.map((stage, i) => {
        const isActive = i === activeIndex;
        const isDone = i < activeIndex;
        return (
          <li key={stage}>
            <motion.span
              initial={false}
              animate={{
                opacity: isDone || isActive ? 1 : 0.35,
                scale: isActive ? 1.04 : 1,
              }}
              transition={{ type: "spring", stiffness: 100, damping: 20 }}
              className={`inline-block rounded-full border px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] ${
                isDone
                  ? "border-[var(--color-grounded)] text-[var(--color-grounded)]"
                  : isActive
                    ? "border-[var(--color-grounded)] text-[var(--color-text)]"
                    : "border-[var(--color-border)] text-[var(--color-muted)]"
              }`}
            >
              {stage}
            </motion.span>
          </li>
        );
      })}
    </ol>
  );
}
