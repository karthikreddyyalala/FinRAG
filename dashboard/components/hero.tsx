import { HeroReplay } from "@/components/hero-replay";
import { Cited } from "@/components/cited";

export function Hero() {
  return (
    <section className="relative overflow-hidden px-4 pb-16 pt-12 md:px-8 md:pt-20">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-text) 1px, transparent 1px), linear-gradient(90deg, var(--color-text) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
          maskImage: "radial-gradient(ellipse 80% 60% at 50% 0%, black 40%, transparent 100%)",
        }}
      />
      <div className="relative mx-auto grid max-w-[1400px] gap-12 md:grid-cols-2 md:items-center">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-4xl font-extrabold leading-none tracking-tighter md:text-6xl">
            Financial answers you can check.
          </h1>
          <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-[var(--color-muted)]">
            FinRAG MCP gives Claude, Cursor, or any MCP client answers grounded in{" "}
            <Cited metric="filings_count" /> SEC filings, and flags any number it can&apos;t find in the source.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href="https://github.com/karthikreddyyalala/FinRAG"
              target="_blank"
              rel="noopener noreferrer"
              className="flex cursor-pointer items-center justify-center rounded-full bg-[var(--color-grounded)] px-6 py-3 text-sm font-semibold text-[var(--color-bg)] transition-transform duration-200 active:translate-y-[1px] active:scale-[0.98]"
            >
              Read the code
            </a>
            <a
              href="#deploy"
              className="flex cursor-pointer items-center justify-center rounded-full border border-[var(--color-border)] px-6 py-3 text-sm font-semibold text-[var(--color-text)] transition-transform duration-200 active:translate-y-[1px] active:scale-[0.98]"
            >
              Deploy your own
            </a>
          </div>
        </div>
        <HeroReplay />
      </div>
    </section>
  );
}
