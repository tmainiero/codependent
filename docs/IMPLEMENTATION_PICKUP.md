# codependent.sty — IMPLEMENTATION PICKUP POINT

> **If you are a fresh orchestrator, READ ALL OF THIS FILE FIRST.**
> **DO NOT SKIP. Skipping has caused repeated regressions.**

## One-sentence state (as of 2026-05-26)

Post-W05-XPARSE-VMODE-FIXES SHIPPED state: HEAD `f520bc8` on `xparse-compatibility`; suite `205 total / passed=204 / failed=1 / pinned-broken=1` with exit 0 (the +17.9pt theorem→proof vmode regression is closed; appendix dagger is DELETED globally; `\@begintheorem` shim wraps theorem-name with hyperlink; central `\codep@emit@destination` helper + LD1 lint shipped; new wire-format baseline `testfiles/baselines/W05-XPARSE-VMODE-FIXES/`); next action: plan W05-XPARSE-SUB-EFFECT (sibling prophylactic substrate work — LD2 effect field + LD3 typed installer + broader lint).

## Next-orchestrator entrypoint (read in order)

1. **This file** — done.
2. **`~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/MEMORY.md`** — durable findings index. Skim the top section + any entry referenced by your task.
3. **W05-XPARSE-SUB-EFFECT planning** — sibling wave deferred from W05-XPARSE-SUBSTRATE-EXTENSION decomposition. Scope locked in `~/.claude/projects/.../memory/project_w05_xparse_vmode_fixes_pickup.md` §"Sibling wave: W05-XPARSE-SUB-EFFECT (DEFERRED)". Not yet planned.
4. **Stray-atom-number deferred bug** — `~/.claude/projects/.../memory/project_stray_atom_number_after_example.md` documents a pre-existing render-pathway bug (orphan paragraph numbers in stress-ta-appendix-gray) that the dagger removal made more visible. Three distinct firing patterns documented. Candidate landing wave: SUB-EFFECT or own micro-wave.
5. **W05 design ledger** — `~/.claude/projects/.../memory/project_w05_design_ledger.md` remains authoritative for D1–D4 decisions. W05-E is PARKED (resume after VMODE-FIXES + SUB-EFFECT + BACKENDS all ship).
6. **`docs/CONVENTIONS.md`** — coding conventions for .sty files (mandatory `@behavior`/`@implements`/`@utility` tagging).
7. **`docs/BEHAVIOR.md`** — behavioral specification (97 testable behavior IDs). Note: B-LINK-APPENDIX-BIDIR clause 1 was reworded in W05-XPARSE-VMODE-FIXES P03 (`b74f80b`) — dagger references replaced with "typeset theorem name (amsthm-family backends)".

## Current suite state (as of HEAD `f520bc8`)

- `205 total / passed=204 / failed=1 / pinned-broken=1 / real-failures=0 / exit=0`
- **Real failures = 0.** The one reported failure is pinned-broken: `test-starred-visible`, deferred via `project_w05_pin1_defer_starred_theorem_numbering.md`.
- Ratchet: `uncovered_behaviors=5`, `unclassified_macros=0`, `test-behavior-baseline=0` — all locked by `.claude/baseline-sizes.json`, **must monotonically shrink**, never grow.
- Linters: 3/3 PASS.

## Verification checkpoint — MANDATORY before any .sty edit

```sh
# 1. Confirm passing baseline
nix develop --command python3 scripts/run-tests.py 2>&1 | tail -3
# Expect: TOTAL: 205  passed=204  failed=1  pinned-broken=1

# 2. Linters all clean
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Confirm branch + HEAD
git rev-parse HEAD              # f520bc8 or later
git rev-parse --abbrev-ref HEAD # xparse-compatibility
```

## W05-XPARSE wave family (decomposed 2026-05-24, further decomposed 2026-05-25)

The original 8-item W05-XPARSE was split into 3 sub-waves at planner-rev round 4 (decomposition pattern: `feedback_wave_decomposition_trigger.md`). SUBSTRATE was further split during planning of its extension wave when both reviewers independently flagged co-equal-goal bundling — the bug-fix subset (VMODE-FIXES) shipped first; SUB-EFFECT (prophylactic substrate work) is its sibling.

| Sub-wave | Scope | Status |
|---|---|---|
| **W05-XPARSE-SUBSTRATE** | 5-slot lifecycle API + cmd-hook rewire + dispatch seam; byte-equivalent to W05-D | **SHIPPED 2026-05-24** `50821e3` |
| **W05-XPARSE-VMODE-FIXES** | central `\codep@emit@destination` helper + LD1 lint + `\@begintheorem` shim + dagger DELETE + ntheorem deferral + baseline rotation | **SHIPPED 2026-05-26** `ab0771a..f520bc8` (4 commits) |
| W05-XPARSE-SUB-EFFECT | LD2 descriptor `effect` field + LD3 typed installer + 5-effect taxonomy + broader lint + 52-row per-callback effect inventory | **NEXT** — not yet planned. Sibling deferred from SUBSTRATE-EXTENSION decomposition. |
| W05-XPARSE-BACKENDS | xparse-generic + keytheorems (quirks-row) + tcolorbox (quirks-row) | future — gated behind SUB-EFFECT |
| W05-XPARSE-HYGIENE | etoolbox Tier-1 sweep (~100 sites) + dead-code (10+2 macros) + behavior-tag migrations | future |

5-slot temporal lattice LOCKED in SUBSTRATE: `pre-begin → post-begin → pre-end → post-end → after-env`. Descriptor `{strategy, quirks-key}` with 1-arm dispatch (extends to `{strategy, quirks-key, effect}` in SUB-EFFECT).

## W05-XPARSE-VMODE-FIXES follow-ons

- 2026-05-26: ntheorem appendix forward navigation is deferred; see `.claude/agent_memory/decisions.md` 2026-05-26 entry.
- 2026-05-26: pre-existing render-pathway bug (orphan atom numbers in stress-ta-appendix-gray PDF body) made more visible by dagger removal; three firing patterns documented in `~/.claude/projects/.../memory/project_stray_atom_number_after_example.md`. Candidate landing wave: SUB-EFFECT or own micro-wave.
- TD-01 (mutool link-annotation stripping in layout-parity directive): DORMANT-FIX; not blocking. Body alignment in P03 rework made the synthetic-marker code path irrelevant for real mutool output.

## W05-D — SHIPPED 2026-05-23 (historical)

Pending-text retirement + dictionary unification. Retired `\codep@pendingbr`/`\codep@queuebackref`/`\codep@flushbackref`. All 4 render paths (theorem/proof/manual/paragraph) now read `\codep@rendered@<key>` cache via `\codep@render@refresh{key}` + `\codep@render@flushbackref{key}`. Added `\codepbackrefsof{label}` additive public sibling. Wire-format 31/31 byte-identical at X1; 28/31+3 intentional at X3. 10k-atom scale probe: lualatex passes; pdflatex/xelatex hit `pool_size` ceiling (engine ceiling, see `docs/SCALING.md`). Commits `6f7c839..ee05da9` (5 commits).

## W05-C — SHIPPED 2026-05-21 (historical)

Axis A (D3 delayed adjacent-commit refactor): replaced "commit immediately then retract" with "store adjacent as candidate, run heading scan, commit once at end". Wire-format-invariant. Commits `236d543..583ab51`.

Axis B (external thmstyle compat): `thmtools[continued]` GREEN fixture landed (`4cc5eff`). `keytheorems` was waived in W05-C; the W05-XPARSE wave above is the follow-on that delivers keytheorems compat.

## Wave history

| Wave | What | Status | Tag/commit |
|------|------|--------|-----------|
| W01–W04 | Phase 3 graph redesign (state machine → atom IDs, .aux/.cdp v2, render barrier) | DONE | various, pre-770ad46 |
| W05-HYG2 | Hygiene + vendored stress fixtures | DONE | |
| W05-A1+RENAME | `pproof:` → `unresref:` rename | DONE | |
| W05-A2 | Joint-proof atom-identity refactor (D1+D2) | DONE | `e3ef8bc..666575d` |
| W05-DEBT | Retire `proof:<display>` alias + named anchor-offset dim | DONE | `770ad46` |
| W05-C | D3 delayed-commit refactor + thmtools-continued | DONE 2026-05-21 | `87c01db` (Axis B); `e264f69` (post-C pickup) |
| W05-DOCS | behavior-ID minting, DESIGN atomic update, CODEMAP stub, IMPLEMENTATION_PICKUP refresh, ratchet shrinkage | DONE | `a0c04b7` |
| W05-PIN1 | Pin-burndown: 10 pinned-broken → 1 remaining pin | DONE | `b12deca` |
| W05-TEST-HYG | Purged root-level v0.1 stubs and `.tlg` siblings; runner guard | DONE | `2bbe790` |
| W05-LINT-HARDEN | Linter hardening | DONE | |
| W05-TAGSWEEP | Macro classification sweep (ratchet shrink to 0) | DONE 2026-05-22 | |
| W05-D | Queue retirement, `\codepbackrefsof`, 10k-atom scale probe | DONE 2026-05-23 | `6f7c839..ee05da9` |
| W05-XPARSE-SUBSTRATE | 5-slot lifecycle API + cmd-hook rewire + dispatch seam | DONE 2026-05-24 | `50821e3` |
| **W05-XPARSE-VMODE-FIXES** | central destination helper + LD1 lint + `\@begintheorem` shim + dagger DELETE + new baseline | **DONE 2026-05-26** | `ab0771a..f520bc8` |
| W05-XPARSE-SUB-EFFECT | LD2/LD3 descriptor `effect` field + typed installer + broader lint + 52-row effect inventory | **NEXT — not yet planned** | |
| W05-XPARSE-BACKENDS | xparse-generic + keytheorems + tcolorbox backends | future (gated behind SUB-EFFECT) | |
| W05-XPARSE-HYGIENE | etoolbox sweep + dead-code + behavior-tag migrations | future | |
| W05-E | `\codepignorethis`, display→atom sidecar, multi-proof ordinal | **PARKED** — resume after W05-XPARSE family ships | |
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
- **Wire-format diff after every `.sty` change** — use `scripts/verify-wire-baseline.py --manifest testfiles/baselines/W05-XPARSE-VMODE-FIXES/baseline.sha256.json` (current wave baseline). Both scripts now accept `--wave <id>` and `--manifest <path>` flags; defaults remain backward-compat.
- **GPT dispatch includes old function bodies** — spec describes target; old code describes current behavior; both required.
- **No fix without a failing test** — write a test first or document as a comment.
- **`kpsewhich` is FORBIDDEN on NixOS** — returns false negatives. Use compile-probes via `nix develop --command pdflatex …` for package availability checks.
- **Wave-decomposition trigger** (new 2026-05-24 per `feedback_wave_decomposition_trigger.md`) — if a planner loop surfaces NEW design-class blockers in 3+ consecutive rounds (vs resolving prior ones), the wave is too large for planner spec-coherence; decompose into smaller substrate-first sub-waves.

## What you are NOT allowed to do

- No big-bang rewrites — wave-based only.
- No editing `codependent.sty` without running the test suite first.
- No running tests outside `nix develop`.
- No declaring a wave done without the current suite floor holding (`205 total / passed=204 / failed=1 / pinned-broken=1`, exit 0 at `f520bc8`).
- No "trust me bro" — every test must pass, zero exceptions.
- No allowlists or new "known-failing" pins (pinned-broken count must monotonically decrease).
- No `git checkout <file>` / `git restore <file>` without saving a patch first.
- No per-package compat shims as the substrate strategy. The W05-XPARSE design uses a **two-strategy + per-package quirks-table** model (per first-principles reviewer); tcolorbox/keytheorems are quirks-rows, not bespoke shims.
- No display-keyed proof identity (`proof:{N.M}`, `proof:1.2`, sidecar aliasing). Canonical proof ID is opaque `proof:a<N>` per `.claude/agent_memory/decisions.md`.

## Key files

| File | What |
|------|------|
| `codependent.sty` | The package (5225+ lines) |
| `codependent-render.sty` | Rendering layer (~590 lines) |
| `README.md` | Repo-root README (added 2026-05-24; GPLv3 inherited from Pavlov dpmac) |
| `docs/PHASE3_SPEC.md` | Phase-3 architecture spec (SHIPPED; historical reference) |
| `docs/BEHAVIOR.md` | Behavioral spec (90+ behavior IDs) |
| `docs/CONVENTIONS.md` | Coding conventions (tagging, naming, indentation) |
| `docs/DESIGN.md` | Living design spec |
| `docs/HISTORY.md` | Audit trail (current through W05-XPARSE-VMODE-FIXES; SUB-EFFECT and later entries TBD per session) |
| `docs/CREDITS.md` | Pavlov dpmac credit |
| `docs/SCALING.md` | 10k-atom scale probe results + engine ceiling notes |
| `docs/COOKBOOK.md` | Worked notes for custom placement of `\codepbackrefs` |
| `scripts/run-tests.py` | Test runner (current suite: 155 unit + 47 integration + 3 stress = 205 fixtures) |
| `scripts/verify-wire-baseline.py` | Wire-format verifier; `--manifest <path>` selects manifest (default: W05-D) |
| `scripts/capture-wire-baseline.py` | Wire-format baseline capture; `--wave <id>` + `--manifest <path>` (default: W05-D) |
| `testfiles/test-index.md` | Generated test index |
| `testfiles/baselines/W05-XPARSE-VMODE-FIXES/baseline.sha256.json` | Wire-format gate (current wave baseline; 31 fixtures) |
| `testfiles/baselines/W05-D/baseline.sha256.json` | HISTORICAL; superseded_by W05-XPARSE-VMODE-FIXES |
| `.claude/scripts/lint_sty_structural.py` | Structural TeX linter |
| `.claude/scripts/lint_traceability.py` | Behavioral traceability check |
| `.claude/scripts/lint-tests.sh` | Test convention linter |
| `.claude/baseline-sizes.json` | Baseline ratchet (monotone shrink) |
| `.claude/paths.toml` | Machine-read doc-path SSOT |
| `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_xparse_vmode_fixes_pickup.md` | HISTORICAL — W05-XPARSE-VMODE-FIXES SHIPPED `ab0771a..f520bc8`; kept for audit + sibling-wave (SUB-EFFECT) scope notes |
| `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_stray_atom_number_after_example.md` | Pre-existing render bug surfaced post-dagger-removal; 3 firing patterns documented; for future micro-wave |

## Test layout

Active `.lvt` fixtures live under `testfiles/unit/` and `testfiles/integration/`:

- `testfiles/unit/*.lvt`: 155 fixtures
- `testfiles/integration/*.lvt`: 47 fixtures (+11 added in W05-XPARSE-VMODE-FIXES P01/P02)
- `testfiles/compiled-examples/`: 3 stress fixture variants
- Total active: 205
- `testfiles/` root: zero `.lvt` fixtures; runner rejects new root-level `.lvt` files

## First commands (next session)

```sh
# 1. Confirm baseline (expect: TOTAL: 205  passed=204  failed=1  pinned-broken=1)
nix develop --command python3 scripts/run-tests.py 2>&1 | tail -3

# 2. Linter state
python3 .claude/scripts/lint_sty_structural.py 2>&1 | tail -3
python3 .claude/scripts/lint_traceability.py 2>&1 | tail -3
.claude/scripts/lint-tests.sh 2>&1 | tail -3

# 3. Recent commits + branch verification
git log --oneline | head -10
git rev-parse --abbrev-ref HEAD  # expect: xparse-compatibility

# 4. Read the most recent wave pickup + the queued bug deferrals
cat ~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_xparse_vmode_fixes_pickup.md  # historical, scope notes for SUB-EFFECT in §"Sibling wave"
cat ~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_stray_atom_number_after_example.md
```

## Pickup files

The next wave (W05-XPARSE-SUB-EFFECT) has NOT been planned yet. Scope notes for it live in `project_w05_xparse_vmode_fixes_pickup.md` §"Sibling wave: W05-XPARSE-SUB-EFFECT (DEFERRED)". A fresh planner brief will be needed.

HISTORICAL pickups (audit trail, do NOT re-execute):

- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_xparse_vmode_fixes_pickup.md` — HISTORICAL (VMODE-FIXES shipped 2026-05-26).
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_xparse_substrate_pickup.md` — HISTORICAL (SUBSTRATE shipped 2026-05-24 at `50821e3`).
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_d_pickup.md` — HISTORICAL (W05-D shipped 2026-05-23 at `ee05da9`).
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_e_pickup.md` — PARKED (resume after VMODE-FIXES + SUB-EFFECT + BACKENDS all ship).
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_design_ledger.md` — D1-D4 decisions still authoritative; wave order in §"2026-05-18 — Post-A2 + DEBT update".
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_w05_consolidated_history.md` — wave history through W05-DEBT (HISTORICAL).
- `~/.claude/projects/-home-cornholio-Documents-research-ai-codependent/memory/project_keytheorems_xparse_future_wave.md` — keytheorems compat scope; deferred to W05-XPARSE-BACKENDS.
