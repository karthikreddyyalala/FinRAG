"use client";
import { useEffect, useState } from "react";
import { GithubLogoIcon } from "@phosphor-icons/react";
import { ThemeToggle } from "@/components/theme-toggle";
import { NAV_LINKS, GITHUB_URL } from "@/lib/constants";

export function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 8);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-40 w-full backdrop-blur-md transition-[border-color] duration-200 ${
        scrolled ? "border-b border-[var(--color-border)]" : "border-b border-transparent"
      }`}
      style={{ backgroundColor: "color-mix(in srgb, var(--color-bg) 80%, transparent)" }}
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-[var(--color-grounded)] focus:px-4 focus:py-2 focus:text-[var(--color-bg)]"
      >
        Skip to content
      </a>
      <nav className="mx-auto flex max-w-[1400px] items-center justify-between px-4 py-4 md:px-8">
        <a
          href="#main"
          className="font-[family-name:var(--font-display)] text-lg font-bold tracking-tight text-[var(--color-text)]"
        >
          FinRAG MCP
        </a>
        <ul className="hidden gap-6 md:flex">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="text-sm text-[var(--color-muted)] transition-colors duration-200 hover:text-[var(--color-text)]"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex cursor-pointer items-center gap-2 rounded-full border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)] transition-transform duration-200 active:scale-[0.98]"
          >
            <GithubLogoIcon size={16} weight="regular" />
            <span className="hidden sm:inline">GitHub</span>
          </a>
        </div>
      </nav>
    </header>
  );
}
