import { describe, it, expect } from "vitest";
import { getMetric } from "./metrics";

describe("getMetric", () => {
  it("returns a known metric", () => {
    const m = getMetric("numerical_accuracy_financebench");
    expect(m.display).toBe("91.0%");
    expect(m.source_file).toBe("evals/results/latest.json");
  });

  it("throws on an unknown key so a typo fails loudly instead of rendering blank", () => {
    expect(() => getMetric("does_not_exist")).toThrow();
  });
});
