# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh orchestrator, READ ALL OF THIS FILE FIRST.**
> **DO NOT SKIP. Skipping has caused repeated regressions.**

> **[2026-06-09 SCOPE-LOCK NOTICE]** As of 2026-06-09 the project is committed to an **L3 REWRITE** on branch `l3-rewrite` (not yet created — pending W0). The body of this doc below describes the pre-rewrite W05-* state on the now-merged `xparse-compatibility` → `main` line; treat it as historical reference. For any new orchestration work, **READ FIRST**:
> - `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_l3_rewrite_architecture.md` (locked architectural decisions across 8 dispatched explorations)
> - MEMORY.md preamble (current `HEAD`, current `main`, immediate NEXT ACTION = 1-day Haskell spike)
>
> Branch line below (`xparse-compatibility`) is no longer current — that branch was fast-forwarded into `main` and deleted on 2026-06-09. Current branch is `main`. Suite-state counts in the one-sentence-state below predate the L3 scope-lock; the implementation pipeline is now W0-tooling-lift, not `W05-BACKENDS-SMOKE-RECLASSIFY`.

## One-sentence state (as of 2026-06-08)

Post-W05-WARNING-HYGIENE SHIPPED (warning oracle + ratchet; no wire rotation): HEAD is `ddb0a17` on `xparse-compatibility`; suite `272 total / passed=269 / failed=3 / pinned-broken=3` with exit 0; W05-WARNING-HYGIENE added `TEST-REQUIRES-WARNING:` / `TEST-TOLERATES-WARNING:` directives + zero-undeclared-non-codependent-warnings gate + `lint_fixture_warnings.py` ratchet; W05-PARA-ORPHAN-FIX eliminated spurious paragraph-atom allocation during theorem teardown (`\codep@teardownpara@suppressdepth` guard, 9 commits, suite floor raised from 263+1 to 269+1); W05-STRESS-WARNINGS cleared overfull \hbox warnings on 3 stress fixtures (wire baseline rotated to `W05-STRESS-WARNINGS`); pinned-broken=3 split is 1 pre-existing (`test-starred-visible`) + 2 new selftest expected-fail fixtures; next action: `W05-BACKENDS-SMOKE-RECLASSIFY` (rename 6 `stress-backends-*` → smoke).

## Next-orchestrator entrypoint (read in order)

1. **This file** — done.
2. **`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/MEMORY.md`** — durable findings index. Skim the headline + top 20 entries. Load-bearing entries (marked **LOAD-BEARING**) are non-negotiable.
3. **`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_session_pickup_2026_06_08.md`** — most recent session pickup (2026-06-08; 3 waves shipped: W05-PARA-ORPHAN-FIX + W05-STRESS-WARNINGS + W05-WARNING-HYGIENE).
4. **`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/feedback_surface_acceptance_tier.md`** — LOAD-BEARING brief-discipline policy (L0–L4 surface tiers; choose acceptance checks by change blast-radius; lint-only briefs save ~15 min vs full-suite tax).
5. **`W05-BACKENDS-SMOKE-RECLASSIFY`** — top of queue. Rename 6 `stress-backends-*` fixtures to smoke classification. Scope in `~/.claude/projects/.../memory/project_w05_backends_smoke_reclassify_future_wave.md`.
6. **`docs/CONVENTIONS.md`** — coding conventions for `.sty` files (mandatory `@behavior`/`@implements`/`@utility` tagging).
7. **`docs/BEHAVIOR.md`** — behavioral specification.

## Current suite state (as of W05-WARNING-HYGIENE wave-close)

- `272 total / passed=269 / failed=3 / pinned-broken=3 / real-failures=0 / exit=0`
- **Real failures = 0.** pinned-broken=3 splits: `test-starred-visible` (pre-existing, deferred via `project_w05_pin1_defer_starred_theorem_numbering.md`) + `selftest-requires-stale-fails` + `selftest-undeclared-fails` (new W05-WARNING-HYGIENE P01 selftest expected-fail fixtures).
- Ratchet: `.traceability-baseline` + `.test-behavior-baseline` + `.claude/baseline-sizes.json` all monotonically shrinking — **must never grow**, never `--update-ratchet` to unblock a growth.
- Warning ratchet: `.claude/baseline-warning-annotations.json` — separate shrink-only ratchet for `TEST-REQUIRES-WARNING` / `TEST-TOLERATES-WARNING` annotations, owned exclusively by `lint_fixture_warnings.py`. Never grow; `--update-ratchet` refused on growth.
- Linters: `lint_sty_structural.py`, `lint_install_discipline.py` (ERROR-tier active), `lint_traceability.py`, `lint-tests.sh`, `lint_fixture_warnings.py` all PASS.
- Wire baseline: `testfiles/baselines/W05-STRESS-WARNINGS/baseline.sha256.json` (71/71 fixtures; rotated at W05-STRESS-WARNINGS wave-close after stress fixture content changes).
- Wall-time: ~160s on 8-core (`--jobs` default `os.process_cpu_count()`); ~503s with `--jobs 1` (sequential).
- Runner env: `max_print_line=10000` (set by runner to disable TeX soft-wrapping in logs — **not a bug**, required for log assertions to match full log lines).

## Verification checkpoint — MANDATORY before any `.sty` edit

```sh
# 1. Confirm passing baseline (parallel — ~3 min on 8-core)
nix develop --command python3 scripts/run-tests.py --full 2>&1 | tail -3
# Expect: TOTAL: 272  passed=269  failed=3  pinned-broken=3

# 2. Linters all clean (~5 sec total)
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_install_discipline.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3
python3 .claude/scripts/lint_fixture_warnings.py 2>&1 | tail -3

# 3. Wire baseline byte-equivalence (~6 min)
nix develop --command python3 scripts/verify-wire-baseline.py \
  --manifest testfiles/baselines/W05-STRESS-WARNINGS/baseline.sha256.json 2>&1 | tail -3

# 4. nix flake check (CI mirror)
nix flake check 2>&1 | tail -3

# 5. Confirm branch + HEAD
git rev-parse HEAD              # ddb0a17 or later
git rev-parse --abbrev-ref HEAD # xparse-compatibility
```

**Surface-acceptance policy**: don't run all five for every change. Match check selection to the L0–L4 surface tier of your change per `feedback_surface_acceptance_tier.md`. Lint-only edits skip the suite + wire + flake (~15 min saved per dispatch).

## Install-discipline contract (LOCKED 2026-06-03)

The W05-INSTALL-DISCIPLINE-CONTRACT family enforces install discipline mechanically. Any new raw install primitive outside the typed substrate or exact named exception is a HARD lint failure (`errors=` line of `lint_install_discipline.py`).

**10 install-kinds (final; not extensible without user sign-off)**:
1. `pretocmd`, 2. `apptocmd`, 3. `AddToHook`, 4. `backend-hook`, 5. `macro-append`, 6. `theorem-name-link-wrap`, 7. `lifecycle-rewrap`, 8. `command-wrap`, 9. `dynamic-command-wrap` (saved body + `\protected\edef#2` dispatcher), 10. `counter-alias` (`\let\csname c@...\endcsname` + `\let\csname the...\endcsname` rebinding).

Typed dispatcher: `\codep@target@install{<install-kind>}{<target>}{<effect>}{<replacement-body>}` at `codependent.sty:1750-1766`.

**2 named non-install exceptions** (exact-anchored; no wildcards):
- `kernel-reset-list-rewrite` at `codependent.sty:995-996` inside `\codep@removefromreset`.
- `enddoc-orchestrator-single-registration` at `codependent.sty:6421`.

**11-row data-append classification table**: 8 codep-owned targets in `DATA_APPEND_ALLOWLIST` (`.claude/scripts/lint_install_discipline.py`), 1 kernel exception (row 2), 2 token-register data-appends (rows 10/11). Full table in `.claude/comms/waves/W05-INSTALL-DISCIPLINE-CONTRACT/install-site-inventory.md` (79 callsites total, machine-traceable).

**Activation-let helper**: `\codep@activation@let@install{target}{callback}` at `codependent.sty:1460-1466` covers 11 pairs in backref + concept hook bodies. Raw `\let\csname X\endcsname\Y` outside this helper or an exact allowlist row FAILS lint.

## Warning-annotation contract (NEW in W05-WARNING-HYGIENE)

Every fixture that emits a non-codependent warning MUST declare it. Two directives in the `.lvt` header:

- `% TEST-REQUIRES-WARNING: <pattern>` — oracle assertion: the warning MUST appear; fail if absent. Use for intentional "warn on misuse" behavior tests.
- `% TEST-TOLERATES-WARNING: <pattern>` — collateral waiver: the warning may appear; do not fail on it. Use for unavoidable third-party warnings (e.g., fontenc, geometry).

**Pattern rules**: must be ≥ 5 characters and not just a broad class name. Broadness rejection is enforced by `lint_fixture_warnings.py`. Prefer extracted-class patterns (e.g., `Font shape 'OT1/cmss/m/n' undefined`) over generic strings.

**Zero-undeclared gate**: the runner fails any fixture that emits an undeclared non-codependent warning. `codependent` package warnings are always exempt (they are the package's own contract).

**Ratchet**: `.claude/baseline-warning-annotations.json` is the annotation ratchet (shrink-only). Do NOT use `lint_traceability.py --update-ratchet` for warning annotations — that ratchet is for traceability baselines only. The warning ratchet is controlled exclusively via `lint_fixture_warnings.py --update-ratchet` (refused on growth).

**Selftest fixtures**: `selftest-requires-stale-fails` and `selftest-undeclared-fails` are pinned-broken expected-fail fixtures that verify the gate machinery; they are counted in pinned-broken=3 and are NOT regressions.

## Wave history (since 2026-05-26 VMODE-FIXES)

| Wave | What | Status | Commits |
|------|------|--------|---------|
| W05-XPARSE-VMODE-FIXES | central destination helper + LD1 lint + `\@begintheorem` shim + dagger DELETE | DONE 2026-05-26 | `ab0771a..f520bc8` |
| W05-INSTALL-DISCIPLINE-CORE | typed installer substrate + 5-effect annotations + Track-2 pin + load-bearing migrations | DONE 2026-05-27 | `487c0fc..eec2ebf` |
| W05-XPARSE-BACKENDS | shared backend resolver + tcolorbox + keytheorems adapters + wire baseline rotation to W05-XPARSE-BACKENDS | DONE 2026-05-28 | `4953cb3..916af04` |
| W05-RESOLVER-SILENT | silent no-track for unnumbered/starred envs (4 backends) | DONE 2026-05-29 | `14b3226` |
| W05-BACKENDS-RICH-STRESS | option/mixed LVTs + 6 rich stress replacements + breakable inline boxes + wire baseline rotation | DONE 2026-06-01 | `a99b81c..d97de0e` |
| W05-RICH-STRESS-FOLLOWUP | hardened 4 SUSPECT-MINOR LVTs from Wave 1 audit (line-preserving; wire still 71/71) | DONE 2026-06-02 | `73837ad` |
| **W05-INSTALL-DISCIPLINE-CONTRACT** | 10 install-kinds + 2 named exceptions + 11-row allowlist + ERROR-mode lint + 79-site inventory | **DONE 2026-06-03** | `f07f01e..0e4b160` (6 commits across 4 sub-waves) |
| **W05-TEST-RUNNER-PARALLEL** | `scripts/run-tests.py` parallelization (3.14× speedup) | **DONE 2026-06-03** | `a86421b` |
| **W05-PRINTKIND-DISPLAY-NAME** | appendix prints title-cased env name instead of display name; universal across 5 backends | **DONE 2026-06-04** | `115fdf4` |
| **W05-PRINTKIND-DISPLAY-OVERRIDE** | `appendix-display=<label>` override key; late-evaluation semantics; 2 unit + 1 integ fixture; **render-only, no wire rotation** | **DONE 2026-06-04** | `eaf0ce9` |
| **W05-HYGIENE-ETOOLBOX-IDIOMS** | 318 etoolbox idiom conversions, LOC −73, structural hygiene | **DONE 2026-06-06** | `3d5f4db` (9 commits) |
| **W05-PARA-ORPHAN-FIX** | `\codep@teardownpara@suppressdepth` guard; eliminates spurious paragraph-atom allocation during theorem teardown; suite 263+1 → 269+1 | **DONE 2026-06-08** | 9 commits |
| **W05-STRESS-WARNINGS** | overfull \hbox warnings cleared on 3 stress fixtures via content shortening; wire baseline rotated to W05-STRESS-WARNINGS | **DONE 2026-06-08** | 2 commits |
| **W05-WARNING-HYGIENE** | TEST-REQUIRES-WARNING + TEST-TOLERATES-WARNING directives; zero-undeclared gate; lint_fixture_warnings.py ratchet; 37 fixtures cleaned + 12 annotated; max_print_line=10000 runner env | **DONE 2026-06-08** | 6 commits |
| W05-BACKENDS-SMOKE-RECLASSIFY | rename 6 `stress-backends-*` fixtures from stress→smoke classification | **NEXT** | — |
| keytheorems-reuse-semantics | restate-forward-link rendering + storestar Option C (bundled fix, 4 surfaces) | queued | — |
| universal unnumbered/starred design decision | sign-off on silent-no-track design across all 5 backends | PARKED (awaiting user sign-off) | — |
| W05-E | `\codepignorethis`, display→atom sidecar, multi-proof ordinal | PARKED | — |
| W05-F | `enabled=false` toggle, `\ref*` macros | future | — |

## Wave history (historical, pre-VMODE-FIXES — for audit only, do NOT re-execute)

| Wave | What | Tag/commit |
|------|------|-----------|
| W01–W04 | Phase 3 graph redesign (state machine → atom IDs, .aux/.cdp v2, render barrier) | various, pre-d773dc7 |
| W05-HYG2 | Hygiene + vendored stress fixtures | DONE |
| W05-A1+RENAME | `pproof:` → `unresref:` rename | DONE |
| W05-A2 | Joint-proof atom-identity refactor (D1+D2) | `ed4e2e1..e9b5389` |
| W05-DEBT | Retire `proof:<display>` alias + named anchor-offset dim | `d773dc7` |
| W05-C | D3 delayed-commit refactor + thmtools-continued | `0000000` |
| W05-DOCS | behavior-ID minting, DESIGN atomic update, CODEMAP stub | `40ee7d8` |
| W05-PIN1 | Pin-burndown: 10 pinned-broken → 1 remaining pin | `9ffad7e` |
| W05-TEST-HYG | Purged root-level v0.1 stubs and `.tlg` siblings | `68a034e` |
| W05-LINT-HARDEN | Linter hardening | DONE |
| W05-TAGSWEEP | Macro classification sweep (ratchet shrink to 0) | DONE 2026-05-22 |
| W05-D | Queue retirement, `\codepbackrefsof`, 10k-atom scale probe | `6f7c839..ee05da9` |
| W05-XPARSE-SUBSTRATE | 5-slot lifecycle API + cmd-hook rewire + dispatch seam | `50821e3` |

The originally-decomposed `W05-XPARSE-SUB-EFFECT` was absorbed into `W05-INSTALL-DISCIPLINE-CORE` (5-effect taxonomy + typed installer substrate). The originally-deferred `W05-XPARSE-HYGIENE` (etoolbox Tier-1 sweep, ~100 sites) was absorbed into `W05-INSTALL-DISCIPLINE-CONTRACT` (P05 mechanical sweep).

## Process rules

- **All tests via `nix develop`** — PDF assertions fail silently otherwise.
- **Tests are now parallel by default** — `--jobs 1` forces sequential; otherwise default is `os.process_cpu_count()`. Sequential mode is only needed for deterministic-order debugging.
- **Runner sets `max_print_line=10000`** — disables TeX log soft-wrapping. This is intentional; log assertions rely on full-line output. Do not treat it as a config error.
- **Orchestrator NEVER edits `.sty`** — dispatch agents, verify their output independently.
- **Every agent dispatch declares a Surface tier** (L0–L4 per `feedback_surface_acceptance_tier.md`) and inherits the matching acceptance check-list. Briefs must NOT pad acceptance with checks the surface can't affect.
- **No hybrid architectures** — pick one approach and commit fully.
- **No parallel old+new state** — each wave's new code is canonical; old code is removed in the same wave.
- **Linters mandatory** — `lint_sty_structural.py`, `lint_install_discipline.py` (ERROR-tier), `lint_traceability.py`, `lint-tests.sh`, `lint_fixture_warnings.py`. Tag every new macro with `@behavior`/`@implements`/`@utility`. Every new `.lvt` needs `TEST-BEHAVIOR: B-X[, B-Y]` header.
- **Baselines monotonically shrink** — never `--update-ratchet` to unblock a growth (applies to all 3 ratchets: traceability-baseline, test-behavior-baseline, baseline-warning-annotations).
- **Unique output filenames** for `agent-dispatch.sh`.
- **Branch before agent edits** — `git checkout -b <wave>-wip`. Every fix is a commit. No working-tree-only state.
- **Wire-format diff after every `.sty` change** — `scripts/verify-wire-baseline.py --manifest testfiles/baselines/W05-STRESS-WARNINGS/baseline.sha256.json` (current wave baseline).
- **Install-discipline lint is ERROR-tier** — any raw install primitive outside the typed substrate or named exception is a HARD failure. The 79-site `install-site-inventory.md` is the authoritative inventory.
- **GPT dispatch includes old function bodies** — spec describes target; old code describes current behavior; both required.
- **`kpsewhich` is FORBIDDEN on NixOS** — returns false negatives. Use compile-probes.
- **Codex coders bypass staging** — known behavior; manifest+target_root must be correct, orchestrator applies via `cp` if `apply-staged.py` can't find the manifest.
- **Wave-decomposition trigger** (`feedback_wave_decomposition_trigger.md`) — if a planner loop surfaces NEW design-class blockers in 3+ consecutive rounds, decompose into smaller sub-waves.
- **Parallel coders require per-coder worktrees** — parallel sonnet coders in a shared working tree will race and corrupt each other's staged state. Use `git worktree add` or serialize. See `feedback_parallel_coders_need_worktrees.md`.

## What you are NOT allowed to do

- No big-bang rewrites — wave-based only.
- No editing `codependent.sty` without running the test suite first.
- No running tests outside `nix develop`.
- No declaring a wave done without the current suite floor holding (`272 total / passed=269 / failed=3 / pinned-broken=3`, exit 0 at post-W05-WARNING-HYGIENE or later).
- No "trust me bro" — every test must pass, zero exceptions.
- No allowlists or new "known-failing" pins (pinned-broken count must monotonically decrease, except selftest expected-fail fixtures which are LOCKED at 2).
- No `git checkout <file>` / `git restore <file>` without saving a patch first.
- No 11th install-kind without explicit user sign-off (10 is locked).
- No wildcard expansion of the 2 named non-install exceptions (`kernel-reset-list-rewrite`, `enddoc-orchestrator-single-registration`) — exact-anchor only.
- No display-keyed proof identity (`proof:{N.M}`, `proof:1.2`, sidecar aliasing). Canonical proof ID is opaque `proof:a<N>` per `.claude/agent_memory/decisions.md`.
- No per-package compat shims as the substrate strategy. The W05-XPARSE design uses a **two-strategy + per-package quirks-table** model; tcolorbox/keytheorems are quirks-rows, not bespoke shims.
- No new undeclared non-codependent warnings in fixtures — every third-party warning MUST have `TEST-TOLERATES-WARNING:` or `TEST-REQUIRES-WARNING:` in the `.lvt` header.

## Key files

| File | What |
|------|------|
| `codependent.sty` | The package (~6500 lines) |
| `codependent-render.sty` | Rendering layer (~590 lines) |
| `README.md` | Repo-root README (GPLv3 inherited from Pavlov dpmac) |
| `docs/PHASE3_SPEC.md` | Phase-3 architecture spec (SHIPPED; historical reference) |
| `docs/BEHAVIOR.md` | Behavioral spec (97+ behavior IDs) |
| `docs/CONVENTIONS.md` | Coding conventions (tagging, naming, indentation) |
| `docs/DESIGN.md` | Living design spec |
| `docs/HISTORY.md` | Audit trail |
| `docs/CREDITS.md` | Pavlov dpmac credit |
| `docs/SCALING.md` | 10k-atom scale probe results + engine ceiling notes |
| `docs/COOKBOOK.md` | Worked notes for custom placement of `\codepbackrefs` |
| `scripts/run-tests.py` | Test runner (parallel by default; `--jobs N` flag; sets `max_print_line=10000`) |
| `scripts/verify-wire-baseline.py` | Wire-format verifier; `--manifest <path>` selects manifest (current default: W05-STRESS-WARNINGS) |
| `scripts/capture-wire-baseline.py` | Wire-format baseline capture; `--wave <id>` + `--manifest <path>` |
| `scripts/build-stress-pdf.sh` | Standalone stress PDF builder for visual review |
| `testfiles/test-index.md` | Generated test index |
| `testfiles/baselines/W05-STRESS-WARNINGS/baseline.sha256.json` | Wire-format gate (current shipped manifest) |
| `testfiles/baselines/W05-PARA-ORPHAN-FIX/baseline.sha256.json` | HISTORICAL; superseded by W05-STRESS-WARNINGS |
| `testfiles/baselines/W05-PRINTKIND-DISPLAY-NAME/baseline.sha256.json` | HISTORICAL; superseded by W05-PARA-ORPHAN-FIX |
| `testfiles/baselines/W05-BACKENDS-RICH-STRESS/baseline.sha256.json` | HISTORICAL; superseded by W05-PRINTKIND-DISPLAY-NAME |
| `testfiles/baselines/W05-XPARSE-BACKENDS/baseline.sha256.json` | HISTORICAL; superseded by W05-BACKENDS-RICH-STRESS |
| `testfiles/baselines/W05-XPARSE-VMODE-FIXES/baseline.sha256.json` | HISTORICAL; superseded by W05-XPARSE-BACKENDS |
| `.claude/scripts/lint_sty_structural.py` | Structural TeX linter |
| `.claude/scripts/lint_install_discipline.py` | Install-discipline lint (ERROR-tier active; `DEFERRED_INSTALL_DIAGNOSTICS_ARE_ERRORS=True`) |
| `.claude/scripts/lint_traceability.py` | Behavioral traceability check |
| `.claude/scripts/lint-tests.sh` | Test convention linter |
| `.claude/scripts/lint_fixture_warnings.py` | Warning-annotation ratchet (TEST-REQUIRES-WARNING / TEST-TOLERATES-WARNING) |
| `.claude/scripts/lint-fixtures/install-discipline/` | Install-discipline fixture matrix (PASS/FAIL twins for all 10 install-kinds + named exceptions + data-append rows) |
| `.claude/baseline-sizes.json` | Baseline ratchet (monotone shrink) |
| `.claude/baseline-warning-annotations.json` | Warning-annotation ratchet (separate shrink-only; owned by lint_fixture_warnings.py) |
| `.claude/paths.toml` | Machine-read doc-path SSOT |
| `.claude/comms/waves/W05-INSTALL-DISCIPLINE-CONTRACT/install-site-inventory.md` | 79-site authoritative install-callsite inventory |
| `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_session_pickup_2026_06_08.md` | Latest session pickup (READ FIRST after MEMORY.md) |
| `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/feedback_surface_acceptance_tier.md` | LOAD-BEARING brief-discipline policy |

## Test layout

Active fixtures (272 total):

- `testfiles/unit/*.lvt`: unit fixtures
- `testfiles/integration/*.lvt`: integration fixtures
- `testfiles/compiled-examples/`: stress fixture variants (`stress-ta-*` + 6 `stress-backends-*`)
- `testfiles/` root: zero `.lvt` fixtures; runner rejects new root-level `.lvt` files

## First commands (next session)

```sh
# 1. Confirm baseline (~3 min parallel)
nix develop --command python3 scripts/run-tests.py --full 2>&1 | tail -3
# Expect: TOTAL: 272  passed=269  failed=3  pinned-broken=3

# 2. Linter state (~5 sec)
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_install_discipline.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3
python3 .claude/scripts/lint_fixture_warnings.py 2>&1 | tail -3

# 3. Recent commits + branch verification
git log --oneline | head -10
git rev-parse --abbrev-ref HEAD  # expect: xparse-compatibility

# 4. Read the most recent session pickup + headline of MEMORY.md
cat ~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_session_pickup_2026_06_08.md
head -10 ~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/MEMORY.md
```

## Active pickup files (in project memory)

- `project_session_pickup_2026_06_08.md` — **CURRENT** (READ FIRST); 3 waves shipped: W05-PARA-ORPHAN-FIX + W05-STRESS-WARNINGS + W05-WARNING-HYGIENE.
- `project_session_pickup_2026_06_06.md` — historical; ETOOLBOX-IDIOMS shipped.
- `project_session_pickup_2026_06_04.md` — historical: PRINTKIND-DISPLAY-NAME + OVERRIDE shipped.
- `project_session_pickup_2026_06_03.md` — historical: CONTRACT family + parallelization.
- `project_w05_backends_smoke_reclassify_future_wave.md` — **top of queue**.
- `project_keytheorems_reuse_semantics_future_wave.md` — queued.
- `project_unnumbered_starred_tracking_future_decision.md` — PARKED (awaiting user sign-off).
- `project_w05_e_pickup.md` — PARKED (resume after current queue clears).
- `project_w05_design_ledger.md` — D1–D4 decisions still authoritative.
- `project_w05_consolidated_history.md` — wave history through W05-DEBT.

Older pickups (`project_w05_xparse_vmode_fixes_pickup.md`, `project_w05_xparse_substrate_pickup.md`, `project_w05_d_pickup.md`, etc.) are HISTORICAL and may be pruned at the next `/special-exit`.

## Pickup-file freshness policy

This file is the canonical clone-portable pickup. It MUST be refreshed at every `/special-exit` to point at the latest session pickup memory, the current HEAD, the current suite count, the current wire-baseline manifest, and the current queue order. Stale `IMPLEMENTATION_PICKUP.md` has caused agents to act on outdated assumptions (e.g., wrong manifest path, wrong suite floor, wrong "next wave"). Treat its freshness as orchestrator-owned process work — refresh it in the session-wrap commit, do NOT defer.
