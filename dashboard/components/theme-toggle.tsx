"use client";
import { useSyncExternalStore } from "react";
import { SunIcon, MoonIcon } from "@phosphor-icons/react";
import { getStoredTheme, setStoredTheme, subscribeToStoredTheme, type Theme } from "@/lib/theme";

function getSnapshot(): Theme {
  return getStoredTheme() ?? "dark";
}

function getServerSnapshot(): Theme {
  return "dark";
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeToStoredTheme, getSnapshot, getServerSnapshot);

  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", theme);
  }

  function toggle() {
    setStoredTheme(theme === "dark" ? "light" : "dark");
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
