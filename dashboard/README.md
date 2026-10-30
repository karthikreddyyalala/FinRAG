# FinRAG MCP dashboard

The public site for FinRAG MCP: landing page, eval results and a blog post. Live at [dashboard-weld-nine-28.vercel.app](https://dashboard-weld-nine-28.vercel.app).

Next.js App Router, TypeScript, Tailwind, `motion`, and Recharts. Every measured number on the page (counts, scores, latencies) comes from `data/metrics.json` through one `<Cited>` component, which shows its source on hover. See the root [README.md](../README.md) for the full project writeup.

## Running it locally

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Tests

```bash
npx vitest run
```

Covers the theme storage helper, the metrics loader, and the numerical verifier (a TypeScript port of `server/retrieval/numerical_verifier.py`, tested against real cases exported from the Python original).

### A note on `npm audit`

It reports high-severity findings in `braces`, reached through
`eslint-config-next`, `@next/eslint-plugin-next`, `fast-glob` and `micromatch`.
These are dev dependencies used only when linting, never bundled into the site,
and the vulnerability needs attacker-controlled glob patterns to trigger, which
isn't reachable here. `npm audit fix --force` "fixes" it by downgrading
`eslint-config-next` to 14.x, which breaks linting on Next 16. Left as-is
deliberately rather than taking a breaking downgrade for no real exposure.

## Structure

- `app/`: pages, layout, fonts, OG image, favicon, 404
- `components/`: one file per section, plus shared pieces like `<Cited>` and the theme toggle
- `lib/`: typed data access (metrics, recordings, verifier port) and static content (pipeline copy, incidents, deploy steps)
- `data/`: `metrics.json` (eval scores synced by `scripts/sync-metrics.mjs` from `../evals/results/`), `corpus.json` (corpus counts, from `scripts/export_corpus.py`), `live/live-check.json` (from `scripts/live_check.py`) and the three recordings used in the hero replay (from `scripts/record_replays.py`)
- `design-system/`: the design tokens and component specs this site follows

## Updating the numbers

```bash
node scripts/sync-metrics.mjs
```

Reads the real eval results from `../evals/results/` and rewrites `data/metrics.json`. Run it after a new eval, then check the diff before committing, since some values (corpus size, cost figures) are sourced from the root `claude.md` and `README.md` rather than a file this script can read directly.
