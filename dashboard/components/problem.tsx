const FAILURES = [
  {
    title: "Stale training data",
    body: "A model's knowledge cutoff is months old. It has no idea what a company reported last quarter.",
  },
  {
    title: "Invented numbers",
    body: "Ask for a specific figure and you get one — stated with full confidence, sourced from nothing.",
  },
  {
    title: "No citation",
    body: "Even a correct-sounding answer gives you nothing to check it against.",
  },
] as const;

export function Problem() {
  return (
    <section className="px-4 py-24 md:px-8">
      <div className="mx-auto grid max-w-[1400px] gap-10 md:grid-cols-[2fr_1fr]">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
            Ask an LLM about revenue and you get a confident guess.
          </h2>
          <p className="mt-4 max-w-[60ch] text-[var(--color-muted)]">
            Every public company files the real numbers with the SEC every quarter. A plain chat model rarely has
            them, and rarely says so.
          </p>
        </div>
        <div className="divide-y divide-[var(--color-border)]">
          {FAILURES.map((f) => (
            <div key={f.title} className="py-4 first:pt-0">
              <h3 className="font-semibold text-[var(--color-text)]">{f.title}</h3>
              <p className="mt-1 text-sm text-[var(--color-muted)]">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
