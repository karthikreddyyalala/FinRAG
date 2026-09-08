# How This Project Gets Built — Process & Tooling Reference

This documents the workflow used to build FinRAG MCP, so it can be repeated
for Week 2 onward. It's a reference for *how we work*, not a spec for
*what the app does* (that's `claude.md`).

---

## The toolkit: Claude Code "skills"

Claude Code (the CLI) supports **skills** — packaged workflows that get
loaded into a session when they apply, instead of Claude improvising an
approach each time. The skills used on this project come from a plugin
called **"superpowers"** plus one third-party plugin, **"ponytail"**
(anti-overengineering discipline, invoked per CLAUDE.md Phase 13 for
implementation tasks).

Skills used so far, in the order they fired:

| Skill | What it does | When it ran |
|---|---|---|
| `superpowers:writing-plans` | Turns a spec into a bite-sized, TDD-structured implementation plan with exact file paths, exact code, exact test commands — no placeholders allowed | Once, before any code: produced `docs/superpowers/plans/2026-09-06-week1-foundation.md` |
| `superpowers:subagent-driven-development` | Executes a plan by dispatching one fresh subagent per task, then two more subagents to review it, in-session (no handoff to a separate session) | For all 8 Week 1 tasks |
| `superpowers:finishing-a-development-branch` | Standard end-of-branch checklist: verify tests, detect git environment, present merge/PR/keep/discard options | Now, at the end of Week 1 |

---

## Why subagents instead of just writing the code directly

The core idea: **every task gets a fresh AI with no memory of anything
else**, given only the exact task text and just enough context to do it.
Then two *more* fresh AIs — who also don't trust the first one's word for
anything — independently check the work before moving on.

This matters because a single long-running session doing everything
tends to accumulate blind spots: it starts trusting its own earlier
decisions, skims its own code during self-review, and doesn't have the
adversarial distance to actually re-derive "does this match what was
asked, from scratch." Fresh subagents don't have that problem — they have
no stake in the code being right, so they go find out.

### The three-role pattern, per task

```
1. IMPLEMENTER subagent
   - Gets: the exact task spec (file paths, exact test code, exact
     implementation code, exact commit message) + just enough project
     context to understand *why* the task matters
   - Does: TDD (write failing test → confirm it fails → implement →
     confirm it passes) → self-review → commit
   - Reports one of: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT

2. SPEC-COMPLIANCE REVIEWER subagent (fresh, no memory of the implementer)
   - Explicitly told: "do not trust the implementer's report"
   - Independently reads the actual committed code and re-runs the tests
     itself
   - Checks: nothing missing, nothing extra/unrequested, no
     misunderstanding of the ask
   - Reports: ✅ compliant, or ❌ specific issues with file:line refs

3. CODE QUALITY REVIEWER subagent (fresh, only runs after #2 passes)
   - Checks: CLAUDE.md's non-negotiable code standards (type hints,
     docstrings, no hardcoded secrets), file scoping, dead code,
     over-engineering, test coverage proportionate to the task
   - Reports: Strengths / Issues (Critical / Important / Minor) /
     Assessment

If either reviewer finds something worth fixing, the same implementer
subagent gets resumed with the specific fix, then re-reviewed. This loop
repeats until both reviews are clean before moving to the next task.
```

I (the controller/orchestrator in this session) never write task code
myself — I write the *prompts* that brief each subagent, read their
reports, decide whether a finding is worth fixing now vs. deferring, and
keep the overall plan on track. This keeps my own context clean for
coordination instead of filling up with every file's contents.

---

## What this actually caught in Week 1

This wasn't theoretical — the review loop found real bugs before they
shipped:

1. **A commit accidentally included an attribution line** you'd
   explicitly banned — caught by spec review, amended out.
2. **`claude.md` corrections were incomplete on the first pass** — 4
   stale `pdfplumber`/PDF references survived in sections the first edit
   missed. Caught by spec review re-grepping the whole file.
3. **A test fixture bug in my own plan** (`sync_pinecone.py`'s test) — a
   shared mock stream got exhausted after one read, which would've
   silently broken the 2nd/3rd batch assertions. The implementer found
   and fixed it, and flagged the deviation for review rather than hiding
   it.
4. **Pinecone's `Index()` constructor makes a real network call** —
   discovered when the implementer actually ran the MCP SDK by hand
   (not just under mocks) instead of trusting the plan's literal
   `app = create_app(...)` at module level. That pattern would have
   required live Pinecone credentials just to *import* the server module,
   breaking tests and slowing every Lambda cold start. Fixed with a lazy
   `get_app()` pattern.
5. **`html_processor.py` double-counted nested HTML tags** — a `<div>`
   wrapping a `<p>` would get extracted as two overlapping text blocks,
   which would have quietly duplicated content across chunks and skewed
   retrieval later. Caught by code-quality review, fixed before
   `chunker.py` (which depends on this output) was built.
6. **`bootstrap_corpus.py` had no per-filing fault isolation** — one bad
   filing out of ~120 would have aborted the entire ingestion run with no
   partial progress saved. Caught by the final whole-branch review,
   fixed before the real ingestion run happens.
7. **A dead/duplicate code path** (`edgar_client.ingest_company` vs.
   `bootstrap_corpus.py`'s own inline version) — caught only by the
   *final* review that looks across all 8 tasks at once, something no
   single-task review could see.

None of these were things I asked for explicitly — they came from
independent, adversarial verification at each step.

---

## The full Week 1 flow, end to end

```
1. Read claude.md (the project spec) in full
2. Verify every package in the stack against current reality (web
   research) -- found 3 real problems: EDGAR serves HTML not PDF (not
   pdfplumber-compatible), pinecone-client is a dead package name, the
   CrossEncoder reranker can't fit a normal Lambda zip deploy
3. Draw architecture diagrams (Mermaid .mmd sequence diagrams) BEFORE
   any code, per claude.md's own Phase 12 instructions
4. Get explicit user sign-off on the 3 stack corrections
5. superpowers:writing-plans -> full Week 1 plan, task-by-task, with
   real code in every step (no placeholders)
6. superpowers:subagent-driven-development -> for each of 8 tasks:
     implement -> spec review -> [fix loop] -> quality review -> [fix loop]
7. Final whole-branch code review (cross-task integration check)
8. superpowers:finishing-a-development-branch -> push + PR
```

---

## For Week 2 and beyond

Same pattern repeats:
1. `/writing-plans` (or ask for it) to turn the next chunk of `claude.md`
   into a task-by-task plan
2. `/subagent-driven-development` (or ask for it) to execute it with the
   implement → spec-review → quality-review loop per task
3. `/finishing-a-development-branch` to close out

If something in `claude.md` turns out to be wrong once we're building
against it (like the PDF/HTML issue this week), the fix goes in
`claude.md` first, then the plan, per the file's own stated rule: *"If
something in this file is wrong or outdated, fix it here first."*
