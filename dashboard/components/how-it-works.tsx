"use client";
import { useState } from "react";
import { motion } from "motion/react";
import { PIPELINE_COPY } from "@/lib/pipeline-copy";

export function HowItWorks() {
  const [mode, setMode] = useState<"technical" | "simple">("simple");

  return (
    <section className="px-4 py-16 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
            One question, every step shown.
          </h2>
          <div className="relative inline-flex rounded-full border border-[var(--color-border)] p-1">
            {(["simple", "technical"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className="relative cursor-pointer rounded-full px-4 py-1.5 text-sm capitalize"
              >
                {mode === m && (
                  <motion.span
                    layoutId="mode-pill"
                    className="absolute inset-0 rounded-full bg-[var(--color-grounded)]"
                    transition={{ type: "spring", stiffness: 100, damping: 20 }}
                  />
                )}
                <span className={`relative ${mode === m ? "text-[var(--color-bg)]" : "text-[var(--color-muted)]"}`}>
                  {m}
                </span>
              </button>
            ))}
          </div>
        </div>

        <ol className="mt-10 divide-y divide-[var(--color-border)]">
          {PIPELINE_COPY.map((step, i) => (
            <li key={step.id} className="flex gap-4 py-5">
              <span className="font-[family-name:var(--font-mono)] text-sm text-[var(--color-muted)]">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <h3 className="font-semibold text-[var(--color-text)]">{step.stage}</h3>
                <p className="mt-1 max-w-[65ch] text-sm text-[var(--color-muted)]">
                  {mode === "technical" ? step.technical : step.simple}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
