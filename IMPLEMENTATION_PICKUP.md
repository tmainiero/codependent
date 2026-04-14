# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh orchestrator, READ ALL OF THIS FILE FIRST.**
> **DO NOT SKIP. Skipping has caused repeated regressions.**

## One-sentence state (as of 2026-04-13)

Phase 1 (test coverage) is **DONE** (94/94 pass). Wave 2.1 (rename) is **DONE**.
Phase 3 (graph redesign) has a **reviewed spec** (`PHASE3_SPEC.md`, 12 rounds of Codex adversarial review). Implementation has **NOT started**.

## Minimum reading list (in order)

1. **This file** — done.
2. **`PHASE3_SPEC.md`** — the implementation spec. Self-contained. 1050+ lines. Covers target architecture, migration waves, invariants, risks.
3. **`CONVENTIONS.md`** — coding conventions for .sty files.
4. **`DESIGN.md`** — living spec for the CURRENT architecture (will be superseded by Phase 3).
5. **`HISTORY.md`** — audit trail. Read the "What did NOT work" sections.

## Verification checkpoint — MANDATORY

Before editing `codependent.sty`, confirm:

1. Tests are 94/94 pass: `nix develop --command python3 testfiles/run-tests.py 2>&1 | tail -5`
2. You have read `PHASE3_SPEC.md` sections 1-2 (architecture) and section 3 (your wave).
3. You know the big-bang rewrite was tried and reverted. You will NOT repeat it.
4. You know all tests MUST run via `nix develop` (PDF assertions fail without mutool/qpdf).
5. Both linters pass: `python3 .claude/scripts/lint_sty_structural.py` and `.claude/scripts/lint-tests.sh`

## Phase 3 migration waves

| Wave | Goal | Risk | Status |
|------|------|------|--------|
| 1 | Query API shim — rendering layer stops reading graph internals | Low | NOT STARTED |
| 2 | Replace state machine with atom IDs + context stack (old .aux/.cdp) | Medium | NOT STARTED |
| 3 | Switch .aux to opaque ID protocol (44 test fixtures change) | HIGH | NOT STARTED |
| 4 | Switch .cdp to v2 (74 test fixtures change) | Medium-High | NOT STARTED |
| 5 | Remove last prefixed-key compatibility code | Low | NOT STARTED |

**Each wave must leave 94+ tests passing.** No exceptions.

## Process rules

- **All tests via `nix develop`** — PDF assertions fail silently otherwise
- **Orchestrator NEVER edits .sty** — dispatch agents, verify their output
- **Every agent dispatch has**: scope boundary, min assertion count, quality gates, forbidden actions
- **Orchestrator reads every diff** and runs tests independently
- **No hybrid architectures** — pick one approach and commit fully
- **No parallel old+new state** — each wave's new code is canonical; old code is removed in the same wave
- **Linters are mandatory** — `.claude/scripts/lint_sty_structural.py` (179 pre-existing errors to fix during rewrite) and `.claude/scripts/lint-tests.sh` (94/94 clean)
- **Unique output filenames** for agent-dispatch.sh (timestamp or round number)
- **Branch before agent edits** — `git checkout -b wave<N>-wip` immediately after GPT delivers. Every fix is a commit on that branch. No working-tree-only state.
- **Save patch after every successful agent** — `git diff > .claude/comms/wave<N>-checkpoint-<K>.patch` after each fix. Backups are non-negotiable.
- **NEVER `git checkout` or `git restore` on dirty tracked files** — use `git stash` or save a patch first. This has destroyed work.
- **Wire-format diff after every .sty change** — `.claude/scripts/compare-wire-format.sh compare` after every agent edit. Empty diff = correct.
- **GPT dispatch includes old function bodies** — the spec describes the target; the old code describes current behavior. Both are required. Use `extract-old-functions.sh` or include them manually.
- **Verify fix before dispatching** — no speculative fixes. Confirm the diagnosis, check edge cases, then dispatch.
- **No fix without a failing test** — if a fix doesn't change test results, either write a test first or document it as a comment without changing code.

## What you are NOT allowed to do

- No big-bang rewrites — wave-based only
- No editing `codependent.sty` without running the test suite first
- No running tests outside `nix develop`
- No declaring a wave done without ALL tests passing
- No "trust me bro" — every test must pass, zero exceptions
- No allowlists or "known-failing" tests
- No `git checkout <file>` or `git restore <file>` without saving a patch first

## Key files

| File | What |
|------|------|
| `PHASE3_SPEC.md` | Implementation spec (12 rounds of adversarial review) |
| `codependent.sty` | The package (2513 lines, 94/94 tests pass) |
| `codependent-render.sty` | Rendering layer (562 lines) |
| `testfiles/run-tests.py` | Test runner (1388 lines, 28 assertion types) |
| `.claude/scripts/lint_sty_structural.py` | Structural TeX linter (zero false positives) |
| `.claude/scripts/lint-tests.sh` | Test convention linter |
| `.claude/scripts/lint-sty.sh` | Basic .sty linter (grep-based, supplementary) |
| `.claude/settings.json` | Hooks: PostToolUse lint on .sty/.lvt edits, PreCommit lint |
| `CONVENTIONS.md` | Coding conventions |
| `DESIGN.md` | Current architecture spec |
| `HISTORY.md` | Audit trail |

## First commands

```sh
# 1. Confirm passing baseline
nix develop --command python3 testfiles/run-tests.py 2>&1 | tail -5

# 2. Check linter state
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -5
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Read the spec
# PHASE3_SPEC.md — start with sections 1-2, then your wave in section 3

# 4. Recent commits
git log --oneline | head -20
```
