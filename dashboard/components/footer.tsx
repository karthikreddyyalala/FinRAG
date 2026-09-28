"use client";
import { GithubLogoIcon, CloudArrowUpIcon } from "@phosphor-icons/react";
import { GITHUB_URL } from "@/lib/constants";

export function Footer() {
  return (
    <footer className="border-t border-[var(--color-border)] px-4 py-12 md:px-8">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-8 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-[family-name:var(--font-display)] text-lg font-bold tracking-tight text-[var(--color-text)]">
            FinRAG MCP
          </p>
          <p className="mt-2 max-w-[40ch] text-sm text-[var(--color-muted)]">
            Karthik Reddy · {new Date().getFullYear()}
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex cursor-pointer items-center justify-center gap-2 rounded-full bg-[var(--color-grounded)] px-5 py-2.5 text-sm font-semibold text-[var(--color-bg)] transition-transform duration-200 active:translate-y-[1px] active:scale-[0.98]"
          >
            <GithubLogoIcon size={16} weight="regular" />
            Read the code
          </a>
          <a
            href="#deploy"
            className="flex cursor-pointer items-center justify-center gap-2 rounded-full border border-[var(--color-border)] px-5 py-2.5 text-sm font-semibold text-[var(--color-text)] transition-transform duration-200 active:translate-y-[1px] active:scale-[0.98]"
          >
            <CloudArrowUpIcon size={16} weight="regular" />
            Deploy your own
          </a>
        </div>
      </div>
      <p className="mx-auto mt-10 max-w-[1400px] font-[family-name:var(--font-mono)] text-xs text-[var(--color-muted)]">
        Every number on this page is cited.
      </p>
    </footer>
  );
}
