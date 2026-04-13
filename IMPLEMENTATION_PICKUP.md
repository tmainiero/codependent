# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh agent, READ ALL OF THIS FILE FIRST. The canonical
> detailed pickup doc is in agent memory — this file points you there.
> DO NOT SKIP. Skipping has caused repeated regressions.**

This file is deliberately short and pointers-only. Full state lives at:

`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_status.md`

Read that file in full before touching anything. Then read `project_pickup_next_session.md`
(linked from the same memory directory).

## The one-sentence state (as of 2026-04-11)

`codependent.sty` is **complete and passing** (77/77 tests, all known bugs fixed).
The next major work is the **graph redesign** — a 5-wave migration to opaque atom IDs
and an explicit context stack. The big-bang approach was tried and reverted; use waves only.

## Minimum reading list (in order)

1. **This file** — done.
2. **`~/.claude/.../memory/project_status.md`** — current test count, bug list, architecture
3. **`~/.claude/.../memory/project_pickup_next_session.md`** — where to start work
4. **`DESIGN.md`** — living spec (updated this session)
5. **`HISTORY.md`** — chronological audit trail; "What did NOT work" register must be read
6. **`CREDITS.md`** — GPLv3 attribution; read before any edit
7. **`.claude/comms/codex-spec-review.md`** — Codex adversarial review of redesign spec (4 BLOCKERs, all resolved)
8. **`.claude/agent_memory/graph_redesign_final.md`** — synthesized 5-wave spec
9. **`.claude/agent_memory/test_gap_analysis.md`** — top 20 missing tests

## Verification checkpoint — MANDATORY

Before editing `codependent.sty`, confirm:

1. Tests are 77/77 pass: `python3 testfiles/run-tests.py 2>&1 | tail -5`
2. You know why the big-bang rewrite was reverted and will not repeat it.
3. You have read the 5-wave migration plan and understand Wave 1's scope.
4. You have read the test gap analysis and know which negative assertions are missing.
5. You are NOT re-implementing anything already in `project_status.md`'s "BUGS — ALL FIXED" list.

If any answer is no, **stop and read**.

## First commands

```sh
# 1. Confirm passing baseline
python3 testfiles/run-tests.py 2>&1 | tail -5

# 2. Review recent commits
git log --oneline | head -20

# 3. Read the synthesized redesign spec
cat .claude/agent_memory/graph_redesign_final.md

# 4. Read the test gap analysis
cat .claude/agent_memory/test_gap_analysis.md
```

## What you are NOT allowed to do

- No big-bang rewrites — wave-based only (see project_pickup_next_session.md)
- No re-proposing anything in `HISTORY.md`'s failure register
- No editing `codependent.sty` without running the test runner first
- No re-implementing bugs already marked FIXED in `project_status.md`
- No updating `flake.nix` (system-wide `texlive-full` is a documented exception)
- No coupling to mwablab internals (codependent is standalone)
- No content-hash staleness detection (`rerunfilecheck` handles it)
- No declaring appendix mode working until Appendix Bug 6 (all backrefs show same value) is fixed

## Why this file is short

The agent-memory pickup doc is the canonical, detailed reference with full rationale,
forbidden-actions list, and architecture history. This file exists only as a trip-wire
to redirect agents who enter via the repo rather than via agent memory.
