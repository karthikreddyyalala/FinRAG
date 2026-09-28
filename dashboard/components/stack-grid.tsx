"use client";
import { CloudIcon, DatabaseIcon, LightningIcon, ShieldCheckIcon, ClockIcon, ChartBarIcon, MagnifyingGlassIcon, CheckCircleIcon, StackIcon } from "@phosphor-icons/react";

const STACK = [
  { name: "AWS Bedrock", icon: LightningIcon },
  { name: "Pinecone", icon: DatabaseIcon },
  { name: "AWS Lambda", icon: CloudIcon },
  { name: "Cognito", icon: ShieldCheckIcon },
  { name: "DynamoDB", icon: DatabaseIcon },
  { name: "EventBridge", icon: ClockIcon },
  { name: "CloudWatch", icon: ChartBarIcon },
  { name: "SQLite FTS5", icon: MagnifyingGlassIcon },
  { name: "ragas", icon: CheckCircleIcon },
  { name: "AWS CDK", icon: StackIcon },
] as const;

export function StackGrid() {
  return (
    <section className="px-4 py-24 md:px-8">
      <div className="mx-auto max-w-[1400px]">
        <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tighter md:text-4xl">
          And everything underneath.
        </h2>
        <div className="mt-10 flex flex-wrap gap-x-10 gap-y-6">
          {STACK.map(({ name, icon: Icon }) => (
            <div key={name} className="flex items-center gap-2.5">
              <Icon size={18} weight="regular" className="text-[var(--color-muted)]" />
              <span className="font-[family-name:var(--font-mono)] text-sm text-[var(--color-text)]">{name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
