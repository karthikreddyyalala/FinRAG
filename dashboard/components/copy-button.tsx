"use client";
import { useState } from "react";
import { CopyIcon, CheckIcon } from "@phosphor-icons/react";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API can be unavailable (insecure context, permissions) — fail silently
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? "Copied" : "Copy to clipboard"}
      className="cursor-pointer rounded-lg border border-[var(--color-border)] p-1.5 text-[var(--color-muted)] transition-colors duration-200 hover:text-[var(--color-text)]"
    >
      {copied ? <CheckIcon size={14} weight="bold" className="text-[var(--color-grounded)]" /> : <CopyIcon size={14} weight="regular" />}
    </button>
  );
}
