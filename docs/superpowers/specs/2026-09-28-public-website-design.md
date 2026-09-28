# FinRAG MCP public website — design spec

Phase E of `claude.md` (E1 + E2): a single site, landing page + eval dashboard,
in `dashboard/`, deployed to Vercel.

## North star

FinRAG never states a number it can't trace to a source. The site follows the
same rule: every number on the page is wrapped in one reusable `<Cited>`
component. Hover (desktop) or tap (mobile) draws a hairline "provenance
thread" from the number to a citation card naming its source — a repo file or
an SEC filing + accession number. Footer: "Every number on this page is
cited."

## Decisions (settled 2026-09-28)

| Decision | Choice |
|---|---|
| Hero layout | Split 50/50 — copy/CTA left, live replay demo right |
| Fonts | Cabinet Grotesk (display) + Satoshi (body/UI) + JetBrains Mono (all numbers, tabular-nums) |
| Default theme | Dark, with a toggle; system preference not auto-applied |
| Router | Next.js App Router, Server Components by default |

## Art direction — "The Audited Terminal"

Editorial, quietly confident, audit-report-meets-terminal. Restraint over
spectacle — the "wow" is precision and the provenance-thread interaction, not
glow effects.

- **Colour**: zinc neutrals only (never mix warm/cool greys). One accent,
  "grounded green" (`#45C98F` dark / `#1B7A51` light), because green is
  literally what the verifier means. Amber (`#E0A84F` / `#A86A12`) is a
  functional "flagged" status colour, not a second brand accent. Status is
  never colour-only — grounded gets a check icon, flagged gets a warning icon.
  Every text/background pair verified at 4.5:1, every chart mark at 3:1, in
  both themes.
- **Texture**: faint 1px "ledger" grid (~4% opacity) behind hero/metrics,
  radial-masked; film grain on one fixed `pointer-events-none` overlay only;
  one slow ambient accent blob at 6–8% opacity behind the hero. No neon, no
  gradient text, no pure black.
- **Cards**: `rounded-2xl`, 1px border, inner top highlight, tinted diffusion
  shadow — used only where elevation communicates hierarchy.
- **Motion**: spring tokens (stiffness 100, damping 20) and
  `cubic-bezier(0.16,1,0.3,1)` easing defined once, reused everywhere.
  Transform/opacity only. One orchestrated hero load sequence. Scroll-linked
  progress via `motion`'s `useScroll`, no scroll hijacking, no
  `window.addEventListener('scroll')`. Perpetual micro-animations (breathing
  status dot, ticker marquee) isolated in memoised client leaf components.
  Magnetic CTA via `useMotionValue`/`useTransform`, never `useState`.
  `prefers-reduced-motion` resolves every animation to its final state
  instantly.
- **Layout**: asymmetric, `max-w-[1400px]`, generous negative space, single
  column with no horizontal scroll below 768px.

## Sections (in order)

0. Section rail (icon nav, desktop only, ≥1280px)
1. Sticky nav: blurred glass, anchor links, theme toggle, GitHub button
2. Hero: split layout, recorded-query replay (real recording, not a mock),
   pipeline-stage rail, streaming answer, citation chips, replay control +
   3-question picker
3. Metrics band: count-up numbers via `<Cited>` (91.0% numerical accuracy,
   1,030 filings, 70 companies, 164,092 chunks) + a pausable ticker of the 70
   real tickers
4. The problem: asymmetric 2fr/1fr or before/after, not 3 equal cards
5. How it works: sticky pipeline diagram + scrolling stage list with a
   Technical/Simple segmented toggle (`layoutId` pill), stages sourced from
   `diagrams/query-sequence.mmd`
6. The verifier ("the part that says no"): editable-answer demo running a
   TypeScript port of `server/retrieval/numerical_verifier.py`'s matching
   rule, live-flagging edited numbers; tells the real `$1,234`/`$1,234.56`
   substring-bug story
7. The four MCP tools: asymmetric bento grid, each tile replays a real
   request/response JSON
8. "Measured, not claimed": Recharts bar chart (dense/BM25/full pipeline) +
   dumbbell chart (FinanceBench vs custom 48Q), table alternative for both,
   "where it lost" (BM25-only beat the full pipeline) and "what we can't
   explain yet" (low ragas metrics) shown as prominently as the wins
9. "Bugs that looked like answers": incident log, sticky card stack, real
   bugs from `claude.md` (dense results discarded, substring verifier, uuid4
   chunk IDs, wrong-year corpus, unpinned temperature, XBRL prior-year trap)
10. Cost & latency: per-stage latency stacked bar from DynamoDB
    `finrag-query-logs`, cache miss-vs-hit race (23,209 ms vs 67 ms), ~$0.0137/query
11. Stack grid: icon + label grid of the real infra (Bedrock, Pinecone,
    Lambda, Cognito, DynamoDB, EventBridge, CloudWatch, SQLite FTS5, ragas,
    AWS CDK)
12. Deploy your own: numbered steps + copy buttons — never implies visitors
    can use the live Lambda
13. Closing CTA + footer: "Read the code" primary, "Deploy your own"
    secondary; footer credits + "Every number on this page is cited."

Also: dynamic OG image (headline + 91.0% metric), favicon, full metadata,
styled 404.

## Data & provenance

`dashboard/data/metrics.json`: every value is `{value, display, source_file,
source_detail}`. Populated by `dashboard/scripts/sync-metrics.mjs`, which
copies numbers out of `evals/results/` (gitignored) and the chunk cache, and
commits its *output* (the JSON), not the source eval files. `<Cited>` reads
only from this file — no number is hard-coded anywhere else in the UI.

Numbers are fixed by `claude.md`/README as of 2026-09-28 (FinanceBench 91.0%
numerical accuracy / 79.4% faithfulness; custom 48Q 86.2%/85.4%; combined
198Q 89.9%/80.2%; baselines dense-only 86.5%/BM25-only 94.4%/full 91.0%; cost
~$0.0137/query, ~24s latency; cache miss 23,209 ms / $0.007445 vs hit 67 ms /
$0). Never rounded up or invented. Honesty rules from the brief are
non-negotiable: BM25-only beating the full pipeline is shown prominently, low
ragas metrics keep their caveat, CI gate claims stay honest (real
faithfulness ~0.80 vs the 0.85 gate), and the deploy section never implies a
shared/public server.

## Demo recordings

Three real recordings captured against production dependencies (per
`claude.md`'s "live-verify without a Cognito token" recipe), saved as JSON in
`dashboard/data/recordings/`: question, rewritten query, per-stage latency,
answer, citations with chunk text. ~$0.01–0.03 total cost — user approves
before this step runs. `df -h /` checked first; `/tmp/finrag/keyword.sqlite`
removed after.

## Verifier port

TypeScript port of `NUMBER_PATTERN` / boundary-aware matching / magnitude
parsing from `server/retrieval/numerical_verifier.py`. TDD: export ≥20 test
cases from the real Python verifier (including the `$1,234` vs `$1,234.56`
substring case, percentages, billion/million, parenthesized negatives), port
until all pass. UI label: "a TypeScript port of the production verifier's
matching rule."

## Stack & constraints

Next.js (App Router) + TypeScript + Tailwind + `motion` (not GSAP/Framer's
old package name) + Recharts + `@phosphor-icons/react`. Server Components by
default; animated/interactive pieces isolated as `'use client'` leaves.
Static site — no backend, no runtime AWS calls, no secrets in the bundle.
Lighthouse ≥ 90 all categories, CLS < 0.1, fonts self-hosted via
`next/font/local` with `swap`, Recharts sections lazy-loaded below the fold.
Full keyboard reachability, visible focus rings, skip link, `<Cited>` works
on keyboard focus not just hover.

Git: feature branch + PR to `main`, never a direct push. No
`Co-Authored-By: Claude` trailer (standing repo rule). `gh` isn't
authenticated here — push the branch and hand over the compare URL.

## Workflow

Repo structure → screenshot references (mcp-kb-site, sapphire-app) →
brainstorm (this doc) → `ui-ux-pro-max --design-system --persist` (writes
`dashboard/design-system/MASTER.md`) → `superpowers:writing-plans` → record
demo data (after cost approval) → scaffold → build one section at a time,
screenshot-verify at 375/768/1440px × light/dark before moving on → charts →
performance/accessibility pass → deploy.

## Done when

- Site live on Vercel
- Every section screenshot-verified at 3 widths × 2 themes × reduced motion
- Lighthouse ≥ 90
- Verifier port passes parity tests against the real Python verifier
- Every number on the page resolves through `metrics.json` to a real source
- README links to the site
- `claude.md` Phase E (E1/E2) marked done
