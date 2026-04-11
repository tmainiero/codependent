# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh agent being asked to implement `codependent.sty`,
> READ ALL OF THIS FILE FIRST, then read `HISTORY.md`, `DESIGN.md`,
> `CREDITS.md`, and the six review files (see note below on their
> location). DO NOT SKIP. The user has been burned
> ~50% of the time by fresh orchestrators who skim critical
> documents and jump to implementation.**

This file is deliberately short and pointers-only. The canonical
reading list + verification checkpoint + forbidden-actions list
lives at:

`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_status.md`

Read that agent-memory file in full before touching anything in
this repo. It takes ~45-60 minutes to read all the linked docs
properly. Don't try to compress it.

## The one-sentence state

The design phase is **complete** (seven rounds of adversarial
review). `codependent.sty` itself is **still at v0.1** (654 lines);
no v1.0 TeX code exists yet. Your job is the **implementation
phase**: edit `codependent.sty` per `DESIGN.md` Section 8a.6.a–8a.6.m
(explicit line-range edit list), iterating red→green against
the test runner at `testfiles/run-tests.py` (36+ fixtures, all
currently red by design — that's the TDD baseline).

## Minimum reading list (in order)

1. **This file** — done.
2. **`HISTORY.md`** (~450 lines) — chronological project evolution.
   Read the whole thing. Especially the **"What did NOT work"**
   failure register near the end — 11+ items of explicitly
   rejected approaches. Do NOT re-propose them.
3. **`DESIGN.md`** (~3500 lines) — the living spec.
   - Intro + Architecture (first ~100 lines)
   - Section 8a (all subsections 8a.0 through 8a.9, 8a.6.a-m
     especially)
   - Section 8b (LaTeXML binding)
   - Section 9a (sidecar writer + `\codepNewCommand` +
     `\codepNewDocumentCommand` + `\codeptag`)
4. **`CREDITS.md`** (293 lines) — GPLv3 attribution + sed-safety
   discipline. Don't skip.
5. **Adversarial review files** (REVIEW_A through REVIEW_F) —
   six adversarial review files. These live in the mwablab repo
   at `tools/semtex-cli/reviews/` (not yet migrated to this
   standalone repo). Skim each **Headline** section; dig into
   REVIEW_E in detail (it has 3 BLOCKERs that MUST be understood
   before editing).
6. **`testfiles/README.md`** — test runner + fixture format docs
7. **`testfiles/run-tests.py`** — the Python test runner
8. **At least 5 fixtures** from `testfiles/unit/` to understand
   the `%% TEST-*:` metadata convention:
   - `test-setref-cleveref.lvt` (BLOCKER E#1 target)
   - `test-restatable-single.lvt` (BLOCKER E#2 target)
   - `test-section-koma.lvt` (BLOCKER E#3 target)
   - `test-currentatom-clear.lvt` (LIVE DEFECT target)
   - `test-newcommand-tracking.lvt` (new public API)

## Verification checkpoint — MANDATORY

Before you edit `codependent.sty`, you must be able to answer these
without consulting notes. See `project_status.md` (in agent memory) for
full questions + expected answers:

1. Why did the architectural pivot happen? (REVIEW_A + REVIEW_ARCH)
2. Why is `\@setref` NOT sufficient? What are the other sites?
   (REVIEW_E #2)
3. What does §8a.5 fix? (LIVE DEFECT from REVIEW_A #3)
4. What is the `\restatable` guard and save/restore fix?
   (REVIEW_E #1 + §8a.5.a)
5. Why can't we patch `\@startsection`? What do we use instead?
   (REVIEW_E #5, §8a.6.i)
6. What is the forward-reference problem, and how does
   `\Hom` vs `\Hom*` solve it? (§8a.9, domain lesson L11)
7. Which fixtures turn green first when you land §8a.6.a?
   (numbering + kernel-ref)

If you cannot answer any of these, **stop and re-read**. Do
NOT start editing.

## First commands

```sh
# 1. Verify the branch and commit history
git log --oneline | head -15

# 2. Establish the red baseline. Expected: all 36+ fixtures
#    fail. This is CORRECT — the TDD signal.
python3 testfiles/run-tests.py 2>&1 | tail -10

# 3. Read the first edit target (§8a.6.a — \codep@queuebackref
#    rewrite, which wires the existing macro to \codep@collapsebr)
sed -n '/^#### 8a.6.a/,/^#### 8a.6.b/p' DESIGN.md

# 4. Open codependent.sty
$EDITOR codependent.sty

# 5. Iterate: edit -> run runner with --filter -> watch fixtures turn green
python3 testfiles/run-tests.py --filter numbering
```

## What you are NOT allowed to do (short list)

The full list is in `project_status.md` (agent memory). Quick
forbidden-actions summary:

- No editing `codependent.sty` without running the test runner first.
- No re-proposing anything in `HISTORY.md`'s failure register.
- No updating `flake.nix` (system-wide `texlive-full` is a
  documented one-time exception).
- No `\newmath` or alternative names for the command-tracking
  macros (they are `\codepNewCommand` and
  `\codepNewDocumentCommand`, case-exact).
- No reopening the dpmac-port architectural decision.
- No content-hash staleness detection (LaTeX's
  `rerunfilecheck` handles it).
- No coupling to mwablab internals (codependent is standalone).
- No merging the v1 legacy Haskell tool into the CLI
  (separate repos, v1 will be deprecated later).
- No single-patch-site `\@setref` interception (three sites
  required; see REVIEW_E #2).
- No "first occurrence wins" for concept backrefs (use
  `\Hom*` starred marker; see §8a.9 / lesson L11).

## Why this file is so short and why the agent-memory file is so long

The agent-memory pickup doc is the canonical, detailed reference.
It has full reading-order timing, full verification-checkpoint
answers, full forbidden-actions list with rationale, full
"why we rejected X" context. It should be read in full.

This file exists ONLY as a trip-wire: if you are exploring the
repo and somehow missed the memory pickup doc, you see this file
and are sent there immediately. Belt-and-suspenders.
