import { describe, it, expect, beforeEach } from "vitest";
import { getStoredTheme, setStoredTheme } from "./theme";

describe("theme storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when nothing stored", () => {
    expect(getStoredTheme()).toBeNull();
  });

  it("round-trips a stored theme", () => {
    setStoredTheme("light");
    expect(getStoredTheme()).toBe("light");
  });

  it("ignores invalid stored values", () => {
    localStorage.setItem("finrag-theme", "not-a-theme");
    expect(getStoredTheme()).toBeNull();
  });
});
