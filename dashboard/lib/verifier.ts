/**
 * TypeScript port of server/retrieval/numerical_verifier.py's matching rule.
 * Ported line-for-line from the Python source, proven against real cases
 * exported from that file (see scripts/export-verifier-cases.py and
 * lib/verifier-cases.json) — not re-derived from the docstring alone.
 *
 * Matching is by parsed numeric magnitude, not substring: this is what
 * makes "$1,234" fail to match inside a source's "$1,234.56" (the historical
 * production bug this verifier exists to prevent), while still matching a
 * parenthesized negative like source "$(1,577)" against an answer's plain
 * "$1,577" — both parse to the same magnitude, 1577.
 *
 * Deliberately NOT implemented (matches the Python source, which documents
 * this as an open gap, not an oversight): "23,400 million" and "23.4
 * billion" are not treated as equivalent. Suffix words (billion/million/
 * thousand/B/M/K) are part of the matched span but ignored when parsing the
 * magnitude — same as the Python side.
 */

const NUMBER_PATTERN =
  /\$\d[\d,]*(?:\.\d+)?(?:\s?(?:billion|million|thousand|B|M|K))?\b|\d+(?:\.\d+)?%|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b/g;

const NUMERIC_TOKEN = /\d[\d,]*(?:\.\d+)?/;

function numericValue(token: string): number | null {
  const digits = NUMERIC_TOKEN.exec(token);
  if (!digits) return null;
  const parsed = parseFloat(digits[0].replace(/,/g, ""));
  return Number.isNaN(parsed) ? null : parsed;
}

function sourceValues(sources: string): Set<number> {
  const values = new Set<number>();
  const re = new RegExp(NUMERIC_TOKEN.source, "g");
  let match: RegExpExecArray | null;
  while ((match = re.exec(sources)) !== null) {
    const value = numericValue(match[0]);
    if (value !== null) values.add(value);
    if (match[0].length === 0) re.lastIndex++; // guard against zero-width match loops
  }
  return values;
}

function isGrounded(numberText: string, values: Set<number>): boolean {
  const value = numericValue(numberText);
  return value !== null && values.has(value);
}

export function verifyAnswer(answer: string, sourceChunks: string[]): string {
  const values = sourceValues(sourceChunks.join(" "));

  const re = new RegExp(NUMBER_PATTERN.source, "g");
  const matches: { start: number; end: number; text: string }[] = [];
  let match: RegExpExecArray | null;
  while ((match = re.exec(answer)) !== null) {
    matches.push({ start: match.index, end: match.index + match[0].length, text: match[0] });
    if (match[0].length === 0) re.lastIndex++;
  }

  // Rewrite right-to-left by match span so earlier offsets stay valid,
  // mirroring the Python implementation's reversed(list(...)) approach.
  let out = answer;
  for (const m of matches.reverse()) {
    if (isGrounded(m.text, values)) continue;
    out = out.slice(0, m.start) + "[exact figure unavailable in retrieved context]" + out.slice(m.end);
  }
  return out;
}
