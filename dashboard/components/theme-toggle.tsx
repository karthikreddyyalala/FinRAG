"use client";
import { useEffect, useState } from "react";
import { SunIcon, MoonIcon } from "@phosphor-icons/react";
import { getStoredTheme, setStoredTheme, type Theme } from "@/lib/theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = getStoredTheme();
    if (stored) {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    setStoredTheme(next);
  }

  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      className="cursor-pointer rounded-full p-2 text-[var(--color-text)] transition-transform duration-200 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-grounded)]"
    >
      {theme === "dark" ? <SunIcon size={20} weight="regular" /> : <MoonIcon size={20} weight="regular" />}
    </button>
  );
}
