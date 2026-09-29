export type Theme = "light" | "dark";
const KEY = "finrag-theme";

export function getStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function setStoredTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
    window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: theme }));
  } catch {
    // per-viewer convenience only; ignore write failures
  }
}

/** For useSyncExternalStore: notifies subscribers when the stored theme changes. */
export function subscribeToStoredTheme(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}
