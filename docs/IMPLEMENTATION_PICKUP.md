# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh orchestrator, READ ALL OF THIS FILE FIRST.**
> **DO NOT SKIP. Skipping has caused repeated regressions.**

## One-sentence state (as of 2026-05-21)

Phase 3 (graph redesign) is **implemented and shipped** through Wave 5 (W05-A2 + W05-DEBT, HEAD `770ad46` on `graph-redesign-phase3`). **W05-C planning is COMPLETE** (9 adversarial rounds, 2026-05-19/20); the W05-C build wave has NOT started. The next orchestrator dispatches the W05-C build per the locked plan.

## Next-orchestrator entrypoint (read in order)

1. **This file** — done.
2. **`.claude/comms/w05-c-PLAN-FINAL.md`** — the buildable W05-C plan. Includes 7 plan items (W05-P30..P36), residual coder-brief caveats (5 of them, MUST be encoded), pre-build checklist, locked user decisions.
3. **`.claude/comms/w05-c-planner-r9.md`** — canonical R9 plan body with full per-item sections (axis, files_owned, attribution, verification commands).
4. **`.claude/comms/w05-c-explorer-state-machine.md`** — code-grounded characterization of the routeforward/resolver/bindproofparent state machine. **Load-bearing** for the W05-P30 (probe) and W05-P32 (refactor) coder briefs.
5. **`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/MEMORY.md`** — durable findings index. Skim the top section + any entry referenced by your task.
6. **`docs/CONVENTIONS.md`** — coding conventions for .sty files (mandatory `@behavior`/`@implements`/`@utility` tagging).
7. **`docs/BEHAVIOR.md`** — behavioral specification (83+ testable [B-XXX] IDs).
8. **`docs/PHASE3_SPEC.md`** — original Phase-3 architecture spec (historical context for the wave structure; not the current plan).

## Current suite state (as of HEAD `770ad46`)

- `190 total / passed=180 / failed=10 / pinned-broken=10 / no-pdf-assertions=0 / exit=0`
- **Real failures = 0.** All 10 "failures" are pinned-broken (known).
- Ratchet: `uncovered_behaviors=44`, `unclassified_macros=42`, `test-behavior-baseline=12` — all locked by `.claude/baseline-sizes.json`, **must monotonically shrink**, never grow.
- Linters: 3/3 PASS (5–7 pre-existing structural warnings — none new).
- Worktree at session-start: 27 modified paths (pre-W05-C residue from W05-A2/DEBT session). Snapshot frozen at `.claude/comms/w05-c-worktree-baseline.txt`. Build agents must leave these untouched.

## Verification checkpoint — MANDATORY before any .sty edit

```sh
# 1. Confirm passing baseline
nix develop --command python3 testfiles/run-tests.py 2>&1 | tail -3
# Expect: 180 pass / 10 pinned-broken / 0 real failures

# 2. Linters all clean
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Confirm branch + HEAD
git rev-parse HEAD              # 770ad46 or a later W05-C-BUILD commit
git rev-parse --abbrev-ref HEAD # graph-redesign-phase3
```

## W05-C build wave — what it does

C1 axis (Axis A): replace the proof-attribution "commit immediately then retract by enumeration" path with "store adjacent as candidate, run heading scan, commit once at the end". **Wire-format-invariant by design** — final `.aux`/`.cdp` must be byte-identical pre/post; only the *timing* of internal side-effect writes changes. The whole point is removing whack-a-mole fragility in the retraction list.

C2/C3 axis (Axis B): verify codependent works against `keytheorems` and `thmtools`'s `[continued=…]` through generic LaTeX hooks. **Desired outcome: zero `.sty` LOC.** If verification reveals a gap, the right fix is a generic-hook consumption change, NOT a per-package compat shim — propose as STOP-and-discuss follow-up.

**Locked user decisions** (encode in coder briefs):
- Stress-fixture-first WAIVED for C1 (invisible internal refactor; integration probe is the right tool).
- Option A on undefined-heading semantics: preserve current behavior (proof orphaned when `\autoref{<undefined>}` in heading). Adjacent-fallback + warning is a SEPARATE future wave — see `memory://project_proof_orphan_fallback.md`.

## Wave history (graph-redesign-phase3 branch)

| Wave | What | Status | Tag/commit |
|------|------|--------|-----------|
| W01–W04 | Phase 3 graph redesign (state machine → atom IDs, .aux/.cdp v2) | DONE | various, pre-770ad46 |
| W05-HYG2 | Hygiene + vendored stress fixtures | DONE | |
| W05-A1+RENAME | `pproof:` → `unresref:` rename | DONE | |
| W05-A2 | Joint-proof atom-identity refactor (D1+D2) | DONE | `e3ef8bc..666575d` |
| W05-DEBT | Retire `proof:<display>` alias + named anchor-offset dim | DONE | `770ad46` |
| **W05-C** | **D3 delayed-commit refactor + external-thmstyle-compat** | **PLAN DONE 2026-05-20, BUILD NOT STARTED** | n/a yet |
| W05-DOCS | docs/CODEMAP.md split, doc-rename, DESIGN.md sweep | future | |
| W05-PIN1 | Pin-burndown attempt | future | |
| W05-D | Queue retirement, harmonize on `\codepbackrefsof` | future | |
| W05-E | `\codepignorethis`, display→atom sidecar, multi-proof ordinal | future | |
| W05-F | `enabled=false` toggle, `\ref*` macros | future | |

## Process rules

- **All tests via `nix develop`** — PDF assertions fail silently otherwise.
- **Orchestrator NEVER edits `.sty`** — dispatch agents, verify their output independently.
- **Every agent dispatch has**: scope boundary, min assertion count, quality gates, forbidden actions, output path.
- **Orchestrator reads every diff** and runs tests independently.
- **No hybrid architectures** — pick one approach and commit fully.
- **No parallel old+new state** — each wave's new code is canonical; old code is removed in the same wave.
- **Linters mandatory** — `lint_sty_structural.py`, `lint_traceability.py`, `lint-tests.sh`. Tag every new macro with `@behavior`/`@implements`/`@utility`. Every new `.lvt` needs `TEST-BEHAVIOR: B-X[, B-Y]` header.
- **Baselines monotonically shrink** — never `--update-ratchet` to unblock a growth.
- **Unique output filenames** for `agent-dispatch.sh`.
- **Branch before agent edits** — `git checkout -b <wave>-wip`. Every fix is a commit. No working-tree-only state.
- **Save patch after every successful agent**.
- **NEVER `git checkout` / `git restore` on dirty tracked files** — `git stash` or save patch first.
- **Wire-format diff after every `.sty` change** — `.claude/scripts/compare-wire-format.sh compare` (note: hardcoded fixture list; for D3 contract fixtures use explicit `diff -u` on captured baselines per W05-C plan).
- **GPT dispatch includes old function bodies** — spec describes target; old code describes current behavior; both required.
- **No fix without a failing test** — write a test first or document as a comment.
- **`kpsewhich` is FORBIDDEN on NixOS** — returns false negatives. Use compile-probes via `nix develop --command pdflatex …` for package availability checks.

## What you are NOT allowed to do

- No big-bang rewrites — wave-based only.
- No editing `codependent.sty` without running the test suite first.
- No running tests outside `nix develop`.
- No declaring a wave done without ALL tests passing (180/180 + 10 pinned-broken).
- No "trust me bro" — every test must pass, zero exceptions.
- No allowlists or new "known-failing" pins (pinned-broken count must monotonically decrease).
- No `git checkout <file>` / `git restore <file>` without saving a patch first.
- No per-package compat shims (`\@ifpackageloaded{keytheorems}{…}{…}`) — generic hooks only.
- No display-keyed proof identity (`proof:{N.M}`, `proof:1.2`, sidecar aliasing). Canonical proof ID is opaque `proof:a<N>` per `.claude/agent_memory/decisions.md:18-22`.

## Key files

| File | What |
|------|------|
| `codependent.sty` | The package (5225 lines as of `770ad46`) |
| `codependent-render.sty` | Rendering layer (586 lines) |
| `docs/PHASE3_SPEC.md` | Phase-3 architecture spec (historical wave structure) |
| `docs/BEHAVIOR.md` | Behavioral spec (83+ [B-XXX] IDs) |
| `docs/CONVENTIONS.md` | Coding conventions (tagging, naming, indentation) |
| `docs/DESIGN.md` | Living design spec (v2 post-W05-A2/DEBT) |
| `docs/HISTORY.md` | Audit trail |
| `docs/CREDITS.md` | Pavlov dpmac credit |
| `testfiles/run-tests.py` | Test runner (3245 lines, 28+ assertion types) |
| `testfiles/test-index.md` | Generated test index (regenerated by fixture-owning items) |
| `.claude/scripts/lint_sty_structural.py` | Structural TeX linter |
| `.claude/scripts/lint_traceability.py` | Behavioral traceability check |
| `.claude/scripts/lint-tests.sh` | Test convention linter |
| `.claude/scripts/compare-wire-format.sh` | Wire-format diff (hardcoded fixture list; supplement with explicit `diff -u` for new fixtures) |
| `.claude/baseline-sizes.json` | Baseline ratchet (monotone shrink) |
| `.claude/paths.toml` | Machine-read doc-path SSOT |
| `.claude/comms/w05-c-PLAN-FINAL.md` | **W05-C build pickup — read this for the next wave** |
| `.claude/comms/w05-c-planner-r9.md` | Canonical R9 plan body |
| `.claude/comms/w05-c-explorer-state-machine.md` | C1 state-machine ground truth |
| `.claude/comms/w05-c-worktree-baseline.txt` | Frozen worktree-residue snapshot (do-not-touch list) |

## First commands (W05-C build session)

```sh
# 1. Confirm baseline
nix develop --command python3 testfiles/run-tests.py 2>&1 | tail -3

# 2. Linter state
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Recent commits
git log --oneline | head -10

# 4. Read the W05-C pickup
cat .claude/comms/w05-c-PLAN-FINAL.md

# 5. Open the build wave
~/.claude/scripts/wave-open.py --wave W05-C-BUILD \
  --objective "Build W05-C per .claude/comms/w05-c-PLAN-FINAL.md" \
  --dag <path-to-build-dag.json>
```

## Historical pickup files (no longer authoritative)

These remain as context but are SUPERSEDED for orchestration purposes:

- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_c_pickup.md` — pre-planning W05-C scope rationale (2026-05-18). The 9-round planning loop locked finer decisions.
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_design_ledger.md` — D1-D4 decisions still authoritative; wave order in §"2026-05-18 — Post-A2 + DEBT update" still authoritative.
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_consolidated_history.md` — wave history through W05-DEBT.
