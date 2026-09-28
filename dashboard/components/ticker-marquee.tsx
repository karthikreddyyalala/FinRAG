"use client";
import { memo } from "react";
import { TICKERS } from "@/lib/tickers";

export const TickerMarquee = memo(function TickerMarquee() {
  const doubled = [...TICKERS, ...TICKERS];
  return (
    <div className="group overflow-hidden [mask-image:linear-gradient(90deg,transparent,black_10%,black_90%,transparent)]">
      <div className="flex w-max animate-[marquee_40s_linear_infinite] gap-8 py-2 group-hover:[animation-play-state:paused] motion-reduce:animate-none">
        {doubled.map((ticker, i) => (
          <span
            key={`${ticker}-${i}`}
            className="font-[family-name:var(--font-mono)] text-sm tabular-nums text-[var(--color-muted)]"
          >
            {ticker}
          </span>
        ))}
      </div>
    </div>
  );
});
