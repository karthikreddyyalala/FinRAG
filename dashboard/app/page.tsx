import { ThemeToggle } from "@/components/theme-toggle";
import { Cited } from "@/components/cited";

export default function Home() {
  return (
    <main className="min-h-[100dvh] p-8">
      <ThemeToggle />
      <h1 className="mt-8 font-[family-name:var(--font-display)] text-4xl md:text-6xl tracking-tighter leading-none font-extrabold">
        FinRAG MCP
      </h1>
      <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
        Scaffold check — fonts, theme tokens, toggle, and provenance wired up.
      </p>
      <p className="mt-4">
        Numerical accuracy: <Cited metric="numerical_accuracy_financebench" />
      </p>
    </main>
  );
}
