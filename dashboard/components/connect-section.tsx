"use client";
import { CopyButton } from "@/components/copy-button";
import { CONNECT_CLIENTS, DEPLOY_STEPS, LIMITS } from "@/lib/connect-steps";

function CodeBlock({ text }: { text: string }) {
  return (
    <div className="mt-2 flex items-start justify-between gap-3 rounded-xl bg-[var(--color-elevated)] p-3">
      <pre className="min-w-0 flex-1 overflow-auto whitespace-pre-wrap break-all font-[family-name:var(--font-mono)] text-xs leading-relaxed text-[var(--color-text)]">
        {text}
      </pre>
      <CopyButton text={text} />
    </div>
  );
}

export function ConnectSection() {
  return (
    <section id="connect" className="px-4 py-24 md:px-8">
      <div className="mx-auto grid max-w-[1400px] gap-12 md:grid-cols-[1.4fr_1fr]">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
            Add it to Claude. No sign-in.
          </h2>
          <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
            The server is public. Streamable HTTP, one URL.
          </p>
          <ul className="mt-8 space-y-8">
            {CONNECT_CLIENTS.map((c) => (
              <li key={c.title}>
                <h3 className="font-semibold text-[var(--color-text)]">{c.title}</h3>
                <p className="mt-1 max-w-[65ch] text-sm text-[var(--color-muted)]">{c.note}</p>
                <CodeBlock text={c.command} />
              </li>
            ))}
          </ul>
        </div>
        <aside className="md:pt-16">
          <h3 className="font-semibold text-[var(--color-text)]">Limits</h3>
          <ul className="mt-3 divide-y divide-[var(--color-border)]">
            {LIMITS.map((l) => (
              <li key={l} className="py-3 text-sm text-[var(--color-muted)]">
                {l}
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <div id="deploy" className="mx-auto mt-20 max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-2xl font-bold tracking-tighter md:text-3xl">
          Deploy your own.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Want your own limits and your own corpus? These are the exact steps.
        </p>
        <ol className="mt-8 space-y-4">
          {DEPLOY_STEPS.map((step, i) => (
            <li key={step.title} className="flex gap-4">
              <span className="font-[family-name:var(--font-mono)] text-sm text-[var(--color-muted)]">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-[var(--color-text)]">{step.title}</h3>
                <CodeBlock text={step.command} />
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
