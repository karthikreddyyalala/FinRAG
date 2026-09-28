"use client";
import { useEffect, useState } from "react";
import { MagnifyingGlassIcon, ChartBarIcon, ShieldCheckIcon, DatabaseIcon, BugIcon, CloudArrowUpIcon } from "@phosphor-icons/react";

const RAIL_SECTIONS = [
  { id: "how-it-works", icon: MagnifyingGlassIcon, label: "How it works" },
  { id: "verifier", icon: ShieldCheckIcon, label: "The verifier" },
  { id: "tools", icon: DatabaseIcon, label: "Tools" },
  { id: "results", icon: ChartBarIcon, label: "Results" },
  { id: "incidents", icon: BugIcon, label: "Incidents" },
  { id: "deploy", icon: CloudArrowUpIcon, label: "Deploy" },
] as const;

export function SectionRail() {
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-40% 0px -40% 0px" }
    );
    for (const section of RAIL_SECTIONS) {
      const el = document.getElementById(section.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <nav
      aria-label="Section navigation"
      className="fixed left-6 top-1/2 z-30 hidden -translate-y-1/2 flex-col gap-4 xl:flex"
    >
      {RAIL_SECTIONS.map(({ id, icon: Icon, label }) => (
        <a
          key={id}
          href={`#${id}`}
          aria-label={label}
          aria-current={active === id ? "true" : undefined}
          className={`cursor-pointer rounded-full border p-2 transition-colors duration-200 ${
            active === id
              ? "border-[var(--color-grounded)] text-[var(--color-grounded)]"
              : "border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]"
          }`}
        >
          <Icon size={16} weight="regular" />
        </a>
      ))}
    </nav>
  );
}
