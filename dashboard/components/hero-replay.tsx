"use client";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircleIcon, PlayIcon, WarningIcon } from "@phosphor-icons/react";
import { RECORDINGS, citationLabels, type Recording } from "@/lib/recordings";
import { PipelineRail, PIPELINE_STAGES } from "@/components/pipeline-rail";

type Phase = "typing" | "pipeline" | "streaming" | "done";

const TYPE_MS_PER_CHAR = 28;
const STAGE_MS = 220;

/**
 * Keyed by `${recordingIndex}-${runId}` in the parent, so switching
 * recordings or hitting replay remounts this fresh instead of needing to
 * reset state from inside an effect (React's lint rules flag setState
 * synchronously inside an effect body as a smell; a key-based remount is
 * the idiomatic way to get a clean-slate replay here).
 */
function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function ReplayPlayer({ recording }: { recording: Recording }) {
  const reduced = useState(prefersReducedMotion)[0];
  const [phase, setPhase] = useState<Phase>(reduced ? "done" : "typing");
  const [typedChars, setTypedChars] = useState(reduced ? recording.question.length : 0);
  const [stageIndex, setStageIndex] = useState(reduced ? PIPELINE_STAGES.length - 1 : 0);
  const [streamedChars, setStreamedChars] = useState(reduced ? recording.answer.length : 0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (reduced) return;

    for (let i = 1; i <= recording.question.length; i++) {
      timers.current.push(setTimeout(() => setTypedChars(i), i * TYPE_MS_PER_CHAR));
    }
    const typingDone = recording.question.length * TYPE_MS_PER_CHAR;

    timers.current.push(setTimeout(() => setPhase("pipeline"), typingDone + 200));
    PIPELINE_STAGES.forEach((_, i) => {
      timers.current.push(setTimeout(() => setStageIndex(i), typingDone + 200 + i * STAGE_MS));
    });
    const pipelineDone = typingDone + 200 + PIPELINE_STAGES.length * STAGE_MS;

    timers.current.push(setTimeout(() => setPhase("streaming"), pipelineDone + 200));
    const streamStep = Math.max(6, Math.floor(recording.answer.length / 60));
    let streamed = 0;
    let delay = pipelineDone + 200;
    while (streamed < recording.answer.length) {
      streamed = Math.min(streamed + streamStep, recording.answer.length);
      delay += 24;
      const s = streamed;
      timers.current.push(setTimeout(() => setStreamedChars(s), delay));
    }
    timers.current.push(setTimeout(() => setPhase("done"), delay + 150));

    const capturedTimers = timers.current;
    return () => {
      capturedTimers.forEach(clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="mt-4 min-h-[2.5rem] font-[family-name:var(--font-mono)] text-sm text-[var(--color-text)]">
        {recording.question.slice(0, typedChars)}
        {phase === "typing" && <span className="animate-pulse">|</span>}
      </div>

      {(phase === "pipeline" || phase === "streaming" || phase === "done") && (
        <div className="mt-4">
          <p className="mb-2 font-[family-name:var(--font-mono)] text-[11px] text-[var(--color-muted)]">
            {recording.tool} returned {recording.passages.length} passages
          </p>
          <PipelineRail activeIndex={stageIndex} />
        </div>
      )}

      {(phase === "streaming" || phase === "done") && (
        <div className="mt-4 whitespace-pre-line text-sm leading-relaxed text-[var(--color-text)]">
          {recording.answer.slice(0, streamedChars)}
        </div>
      )}
      {phase === "done" && (
        <p className="mt-2 text-[11px] text-[var(--color-muted)]">
          Answer by {recording.model} (eval client). In Claude, your own model writes it.
        </p>
      )}

      <AnimatePresence>
        {phase === "done" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 100, damping: 20 }}
            className="mt-4 flex flex-wrap gap-2"
          >
            {citationLabels(recording).map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1 rounded-full border border-[var(--color-grounded)] px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] text-[var(--color-grounded)]"
              >
                <CheckCircleIcon size={12} weight="fill" />
                {label}
              </span>
            ))}
            {recording.verify.grounded.length > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-grounded)] px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] text-[var(--color-grounded)]">
                <CheckCircleIcon size={12} weight="fill" />
                grounded: {recording.verify.grounded.join(", ")}
              </span>
            )}
            {recording.verify.not_found.length > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-flagged)] px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] text-[var(--color-flagged)]">
                <WarningIcon size={12} weight="fill" />
                not_found: {recording.verify.not_found.join(", ")}
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export function HeroReplay() {
  const [recordingIndex, setRecordingIndex] = useState(0);
  const [runId, setRunId] = useState(0);
  const recording = RECORDINGS[recordingIndex];

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-card)] [box-shadow:var(--shadow-card),inset_0_1px_0_rgba(255,255,255,0.06)]">
      <div className="flex items-center justify-between gap-2">
        <span className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-wide text-[var(--color-muted)]">
          Recorded from the live server
        </span>
        <button
          type="button"
          onClick={() => setRunId((r) => r + 1)}
          aria-label="Replay"
          className="cursor-pointer rounded-full p-1.5 text-[var(--color-muted)] transition-colors duration-200 hover:text-[var(--color-grounded)]"
        >
          <PlayIcon size={16} weight="fill" />
        </button>
      </div>

      <ReplayPlayer key={`${recordingIndex}-${runId}`} recording={recording} />

      <div className="mt-6 flex flex-wrap gap-2 border-t border-[var(--color-border)] pt-4">
        {RECORDINGS.map((r, i) => (
          <button
            key={r.id}
            type="button"
            onClick={() => {
              setRecordingIndex(i);
              setRunId((n) => n + 1);
            }}
            className={`cursor-pointer rounded-full border px-3 py-1 text-xs transition-colors duration-200 ${
              i === recordingIndex
                ? "border-[var(--color-grounded)] text-[var(--color-grounded)]"
                : "border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            {r.id === "mmm-capex-fy2018" ? "3M capex" : r.id === "nvda-revenue-q1fy2027" ? "NVDA revenue" : "TSLA vs F"}
          </button>
        ))}
      </div>
    </div>
  );
}
