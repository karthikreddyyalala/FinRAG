import { ThemeToggle } from "@/components/theme-toggle";

export default function Home() {
  return (
    <main className="min-h-[100dvh] p-8">
      <ThemeToggle />
      <h1 className="mt-8 font-[family-name:var(--font-display)] text-4xl md:text-6xl tracking-tighter leading-none font-extrabold">
        FinRAG MCP
      </h1>
      <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
        Scaffold check — fonts, theme tokens, and toggle wired up.
      </p>
      <p className="mt-4 font-[family-name:var(--font-mono)] tabular-nums text-[var(--color-grounded)]">
        91.0%
      </p>
    </main>
  );
}
