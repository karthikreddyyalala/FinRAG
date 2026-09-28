"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircleIcon, PlayIcon } from "@phosphor-icons/react";
import { RECORDINGS } from "@/lib/recordings";
import { PipelineRail, PIPELINE_STAGES } from "@/components/pipeline-rail";

type Phase = "typing" | "pipeline" | "streaming" | "done";

const TYPE_MS_PER_CHAR = 28;
const STAGE_MS = 220;

export function HeroReplay() {
  const [recordingIndex, setRecordingIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("typing");
  const [typedChars, setTypedChars] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const [streamedChars, setStreamedChars] = useState(0);
  const [runId, setRunId] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const recording = RECORDINGS[recordingIndex];

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => {
    clearTimers();
    setPhase("typing");
    setTypedChars(0);
    setStageIndex(0);
    setStreamedChars(0);

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) {
      setTypedChars(recording.question.length);
      setStageIndex(PIPELINE_STAGES.length - 1);
      setStreamedChars(recording.answer.length);
      setPhase("done");
      return clearTimers;
    }

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

    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingIndex, runId, clearTimers]);

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-card)] [box-shadow:var(--shadow-card),inset_0_1px_0_rgba(255,255,255,0.06)]">
      <div className="flex items-center justify-between gap-2">
        <span className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-wide text-[var(--color-muted)]">
          Recorded from the production pipeline
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

      <div className="mt-4 min-h-[2.5rem] font-[family-name:var(--font-mono)] text-sm text-[var(--color-text)]">
        {recording.question.slice(0, typedChars)}
        {phase === "typing" && <span className="animate-pulse">|</span>}
      </div>

      {(phase === "pipeline" || phase === "streaming" || phase === "done") && (
        <div className="mt-4">
          <PipelineRail activeIndex={stageIndex} />
        </div>
      )}

      {(phase === "streaming" || phase === "done") && (
        <div className="mt-4 whitespace-pre-line text-sm leading-relaxed text-[var(--color-text)]">
          {recording.answer.slice(0, streamedChars)}
        </div>
      )}

      <AnimatePresence>
        {phase === "done" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 100, damping: 20 }}
            className="mt-4 flex flex-wrap gap-2"
          >
            {Array.from(new Set(recording.citations.map((c) => `${c.ticker} ${c.filing_type} ${c.period}`))).map(
              (label) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--color-grounded)] px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] text-[var(--color-grounded)]"
                >
                  <CheckCircleIcon size={12} weight="fill" />
                  {label}
                </span>
              )
            )}
          </motion.div>
        )}
      </AnimatePresence>

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
            {r.id === "mmm-capex-fy2018" ? "3M capex" : r.id === "nvda-revenue-q1fy2026" ? "NVDA revenue" : "TSLA vs F"}
          </button>
        ))}
      </div>
    </div>
  );
}
