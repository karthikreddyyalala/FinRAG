"use client";
import { memo, useEffect, useRef, useState } from "react";
import { motion, useInView } from "motion/react";

/** Animates from 0 to a target display string once, when scrolled into view. */
export const CountUp = memo(function CountUp({ target, durationMs = 900 }: { target: number; durationMs?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!inView) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    const start = performance.now();
    let frame: number;
    function tick(now: number) {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [inView, target, durationMs]);

  return (
    <motion.span ref={ref} className="tabular-nums">
      {Math.round(value).toLocaleString()}
    </motion.span>
  );
});
