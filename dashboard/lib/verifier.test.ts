import { describe, it, expect } from "vitest";
import { verifyAnswer } from "./verifier";
import cases from "./verifier-cases.json";

describe("verifyAnswer parity with the production Python verifier", () => {
  for (const c of cases as { name: string; answer: string; chunks: string[]; expected: string }[]) {
    it(c.name, () => {
      expect(verifyAnswer(c.answer, c.chunks)).toBe(c.expected);
    });
  }
});
