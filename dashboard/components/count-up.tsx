"use client";
import { memo, useEffect, useRef, useState } from "react";

/**
 * Renders `target` immediately, and only animates up to it when the element
 * scrolls into view from off-screen.
 *
 * Starting at 0 would have been simpler, but it meant the server-rendered
 * HTML said "0 SEC filings ingested" until JS ran, which is a bad look on a
 * page whose whole argument is that its numbers are traceable and correct.
 * Rendering the real value server-side also keeps hydration consistent: the
 * first client render matches the server exactly, and the count-up only kicks
 * in afterwards, for the scroll-in case where it reads as an effect rather
 * than a correction.
 */
export const CountUp = memo(function CountUp({
  target,
  durationMs = 900,
}: {
  target: number;
  durationMs?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [value, setValue] = useState(target);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    let firstObservation = true;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          // Already on screen at load: leave the real number alone rather
          // than flashing it back to 0 just to re-count it.
          if (firstObservation) {
            firstObservation = false;
            if (entry.isIntersecting) {
              observer.disconnect();
              return;
            }
            continue;
          }
          if (!entry.isIntersecting) continue;
          observer.disconnect();

          const start = performance.now();
          const tick = (now: number) => {
            const t = Math.min(1, (now - start) / durationMs);
            const eased = 1 - Math.pow(1 - t, 3);
            setValue(target * eased);
            if (t < 1) frame = requestAnimationFrame(tick);
          };
          frame = requestAnimationFrame(tick);
        }
      },
      { rootMargin: "-10% 0px" }
    );

    observer.observe(el);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [target, durationMs]);

  return (
    <span ref={ref} className="tabular-nums">
      {Math.round(value).toLocaleString()}
    </span>
  );
});
