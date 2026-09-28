"use client";
import { useState, useMemo } from "react";
import { motion } from "motion/react";
import { CheckCircleIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { verifyAnswer } from "@/lib/verifier";
import { RECORDINGS } from "@/lib/recordings";

const SOURCE_CHUNK = RECORDINGS[0].citations[0]?.text ?? "";
const BASE_ANSWER = "3M's capital expenditure in fiscal year 2018 was $1,577 million.";

export function VerifierDemo() {
  const [editableNumber, setEditableNumber] = useState("1,577");

  const answer = useMemo(
    () => BASE_ANSWER.replace("1,577", editableNumber),
    [editableNumber]
  );
  const verified = useMemo(() => verifyAnswer(answer, [SOURCE_CHUNK]), [answer]);
  const isFlagged = verified.includes("[exact figure unavailable in retrieved context]");

  return (
    <section id="verifier" className="px-4 py-16 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          The part that says no.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Edit the number below. If it doesn&apos;t match what&apos;s in the source chunk, the verifier flags it —
          live, in your browser. This is a TypeScript port of the production verifier&apos;s matching rule.
        </p>

        <div className="mt-8 grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
            <h3 className="font-[family-name:var(--font-mono)] text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Retrieved source chunk
            </h3>
            <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap font-[family-name:var(--font-mono)] text-xs leading-relaxed text-[var(--color-muted)]">
              {SOURCE_CHUNK}
            </pre>
          </div>

          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
            <h3 className="font-[family-name:var(--font-mono)] text-xs uppercase tracking-wide text-[var(--color-muted)]">
              Generated answer (editable)
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-[var(--color-text)]">
              3M&apos;s capital expenditure in fiscal year 2018 was $
              <input
                type="text"
                value={editableNumber}
                onChange={(e) => setEditableNumber(e.target.value)}
                aria-label="Edit the dollar figure"
                className="inline-block w-24 border-b border-[var(--color-border)] bg-transparent px-1 font-[family-name:var(--font-mono)] tabular-nums focus:border-[var(--color-grounded)] focus:outline-none"
              />{" "}
              million.
            </p>

            <motion.div
              key={isFlagged ? "flagged" : "grounded"}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 100, damping: 20 }}
              className={`mt-4 flex items-start gap-2 rounded-xl border px-3 py-2 text-sm ${
                isFlagged
                  ? "border-[var(--color-flagged)] text-[var(--color-flagged)]"
                  : "border-[var(--color-grounded)] text-[var(--color-grounded)]"
              }`}
            >
              {isFlagged ? (
                <WarningCircleIcon size={18} weight="fill" className="mt-0.5 shrink-0" />
              ) : (
                <CheckCircleIcon size={18} weight="fill" className="mt-0.5 shrink-0" />
              )}
              <span>
                {isFlagged
                  ? "Flagged: this figure doesn't appear in the retrieved source."
                  : "Grounded: this figure appears in the retrieved source."}
              </span>
            </motion.div>
          </div>
        </div>

        <div className="mt-8 rounded-2xl border border-[var(--color-border)] p-6">
          <h3 className="font-semibold text-[var(--color-text)]">The bug this exists to prevent</h3>
          <p className="mt-2 max-w-[65ch] text-sm text-[var(--color-muted)]">
            An early version of this verifier used substring matching: it checked whether{" "}
            <code className="font-[family-name:var(--font-mono)]">&quot;$1,234&quot;</code> appeared anywhere in the
            source text. That passed a fabricated <code className="font-[family-name:var(--font-mono)]">$1,234</code>{" "}
            whenever the source actually said{" "}
            <code className="font-[family-name:var(--font-mono)]">$1,234.56</code> — the shorter string is a literal
            substring of the longer one. The fix compares parsed numeric magnitude instead of text, which is what
            you&apos;re running above.
          </p>
        </div>
      </div>
    </section>
  );
}
