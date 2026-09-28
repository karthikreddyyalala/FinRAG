"use client";
import { CopyButton } from "@/components/copy-button";
import { DEPLOY_STEPS } from "@/lib/deploy-steps";

export function DeploySteps() {
  return (
    <section id="deploy" className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Deploy your own.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          The deployed server behind this page is single-user — there&apos;s no public endpoint to connect to.
          These are the exact steps to run your own.
        </p>
        <ol className="mt-8 space-y-4">
          {DEPLOY_STEPS.map((step, i) => (
            <li key={step.title} className="flex gap-4">
              <span className="font-[family-name:var(--font-mono)] text-sm text-[var(--color-muted)]">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="flex-1">
                <h3 className="font-semibold text-[var(--color-text)]">{step.title}</h3>
                <div className="mt-2 flex items-start justify-between gap-3 rounded-xl bg-[var(--color-elevated)] p-3">
                  <pre className="overflow-auto whitespace-pre-wrap font-[family-name:var(--font-mono)] text-xs leading-relaxed text-[var(--color-text)]">
                    {step.command}
                  </pre>
                  <CopyButton text={step.command} />
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
