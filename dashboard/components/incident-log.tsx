"use client";
import { BugIcon } from "@phosphor-icons/react";
import { INCIDENTS } from "@/lib/incidents";

export function IncidentLog() {
  return (
    <section id="incidents" className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          Bugs that looked like answers.
        </h2>
        <p className="mt-4 max-w-[65ch] text-[var(--color-muted)]">
          Financial RAG fails quietly — a wrong number looks exactly like a right one until you check it. These are
          real bugs from building this system, not hypotheticals.
        </p>

        <div className="mt-12 divide-y divide-[var(--color-border)]">
          {INCIDENTS.map((incident) => (
            <div key={incident.title} className="grid gap-4 py-8 first:pt-0 md:grid-cols-[1fr_2fr]">
              <div className="flex items-start gap-2">
                <BugIcon size={16} weight="regular" className="mt-0.5 shrink-0 text-[var(--color-flagged)]" />
                <h3 className="font-semibold text-[var(--color-text)]">{incident.title}</h3>
              </div>
              <dl className="grid gap-4 sm:grid-cols-3">
                <div>
                  <dt className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-wide text-[var(--color-muted)]">
                    Symptom
                  </dt>
                  <dd className="mt-1 text-sm text-[var(--color-text)]">{incident.symptom}</dd>
                </div>
                <div>
                  <dt className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-wide text-[var(--color-muted)]">
                    Root cause
                  </dt>
                  <dd className="mt-1 text-sm text-[var(--color-text)]">{incident.root_cause}</dd>
                </div>
                <div>
                  <dt className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-wide text-[var(--color-grounded)]">
                    Fix
                  </dt>
                  <dd className="mt-1 text-sm text-[var(--color-text)]">{incident.fix}</dd>
                </div>
              </dl>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
