# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh orchestrator, READ ALL OF THIS FILE FIRST.**
> **DO NOT SKIP. Skipping has caused repeated regressions.**

## One-sentence state (as of 2026-05-21)

W05-C SHIPPED 2026-05-21; suite 192/182/10/0; HEAD `e264f69` on `graph-redesign-phase3`; next wave: W05-PIN1 per design ledger order.

## Next-orchestrator entrypoint (read in order)

1. **This file** — done.
2. **W05-PIN1 brief** — no brief written yet; see `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_design_ledger.md` §"Revised wave order" for scope. W05-PIN1 scope TBD — pin-broken count cleanup per `feedback_no_pinning.md`.
3. **`.claude/comms/w05-docs-planner.md`** — W05-DOCS planner output (P37–P42 items); read for any in-flight DOCS items.
4. **`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/MEMORY.md`** — durable findings index. Skim the top section + any entry referenced by your task.
5. **`docs/CONVENTIONS.md`** — coding conventions for .sty files (mandatory `@behavior`/`@implements`/`@utility` tagging).
6. **`docs/BEHAVIOR.md`** — behavioral specification (96+ testable [B-XXX] IDs).
7. **`docs/PHASE3_SPEC.md`** — original Phase-3 architecture spec (historical context for the wave structure; not the current plan).

## Current suite state (as of HEAD `e264f69`)

- `192 total / passed=182 / failed=10 / pinned-broken=10 / no-pdf-assertions=0 / exit=0`
- **Real failures = 0.** All 10 "failures" are pinned-broken (known).
- Ratchet: `uncovered_behaviors=44`, `unclassified_macros=42`, `test-behavior-baseline=12` — all locked by `.claude/baseline-sizes.json`, **must monotonically shrink**, never grow.
- Linters: 3/3 PASS (5–7 pre-existing structural warnings — none new).

## Verification checkpoint — MANDATORY before any .sty edit

```sh
# 1. Confirm passing baseline
nix develop --command python3 testfiles/run-tests.py 2>&1 | tail -3
# Expect: 182 pass / 10 pinned-broken / 0 real failures

# 2. Linters all clean
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Confirm branch + HEAD
git rev-parse HEAD              # 770ad46 or a later W05-C-BUILD commit
git rev-parse --abbrev-ref HEAD # graph-redesign-phase3
```

## W05-C — SHIPPED 2026-05-21 (historical)

Axis A (D3 delayed adjacent-commit refactor): replaced the proof-attribution "commit immediately then retract by enumeration" path with "store adjacent as candidate, run heading scan, commit once at the end". Wire-format-invariant; final `.aux`/`.cdp` byte-identical pre/post. Commits `236d543..583ab51` (`W05-P30`–`W05-P33`).

Axis B (external thmstyle compat): `thmtools[continued]` GREEN fixture landed (`4cc5eff`). `keytheorems` WAIVED — upstream `xparse`-vs-cmd-hook incompatibility (reproduces without codependent); see [`project_keytheorems_xparse_future_wave.md`](~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_keytheorems_xparse_future_wave.md) for scope of a future wave. Commits `1287f41..87c01db`.

Post-wave DOCS items: `4b0496a` (W05-P37, 7 new B-IDs), `e264f69` (W05-P39, stale proof:N.M comment sweep).

## Wave history (graph-redesign-phase3 branch)

| Wave | What | Status | Tag/commit |
|------|------|--------|-----------|
| W01–W04 | Phase 3 graph redesign (state machine → atom IDs, .aux/.cdp v2) | DONE | various, pre-770ad46 |
| W05-HYG2 | Hygiene + vendored stress fixtures | DONE | |
| W05-A1+RENAME | `pproof:` → `unresref:` rename | DONE | |
| W05-A2 | Joint-proof atom-identity refactor (D1+D2) | DONE | `e3ef8bc..666575d` |
| W05-DEBT | Retire `proof:<display>` alias + named anchor-offset dim | DONE | `770ad46` |
| W05-C | D3 delayed-commit refactor + external-thmstyle-compat (Axis A + Axis B; keytheorems waived — see `project_keytheorems_xparse_future_wave.md`) | DONE 2026-05-21 | `87c01db` (Axis B close); `e264f69` (HEAD post-DOCS) |
| **W05-DOCS** | **B-ID minting, IMPLEMENTATION_PICKUP refresh, ratchet shrinkage** | **IN PROGRESS** | |
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

## First commands (W05-PIN1 / next session)

```sh
# 1. Confirm baseline (expect: 182 pass / 10 pinned-broken / 0 real failures)
nix develop --command python3 testfiles/run-tests.py 2>&1 | tail -3

# 2. Linter state
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Recent commits
git log --oneline | head -10

# 4. Read the design ledger for W05-PIN1 scope
cat ~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_design_ledger.md
```

## Historical pickup files (no longer authoritative)

These remain as context but are SUPERSEDED for orchestration purposes:

- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_c_axis_a_landed.md` — W05-C ship state (HEAD, suite, Axis A + B details). HISTORICAL post-W05-C.
- `.claude/comms/w05-c-PLAN-FINAL.md` — W05-C build plan. HISTORICAL (W05-C shipped).
- `.claude/comms/w05-c-planner-r9.md` — canonical R9 plan body. HISTORICAL (W05-C shipped).
- `.claude/comms/w05-c-explorer-state-machine.md` — D3 state-machine ground truth. HISTORICAL.
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_c_pickup.md` — pre-planning W05-C scope rationale (2026-05-18). HISTORICAL.
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_design_ledger.md` — D1-D4 decisions still authoritative; wave order in §"2026-05-18 — Post-A2 + DEBT update" still authoritative.
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_consolidated_history.md` — wave history through W05-DEBT.
