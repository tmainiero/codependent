# Codependent

LaTeX package for automatic semantic dependency tracking and backreference rendering in mathematical documents. Inspired by Dmitri Pavlov's dpmac (GPLv3).

## Identity

| | Name |
|---|---|
| Package / CTAN | `codependent` (`\usepackage{codependent}`) |
| CLI binary | `codep` |
| Internal prefix | `\codep@` |
| User commands | `\codeptrack`, `\codepsetup`, `\codeptag`, `\codepnewcommand`, etc. |
| pgfkeys namespace | `/codep/` |

## First-time setup (per clone)

```sh
git config core.hooksPath .githooks   # enable repo-shared git hooks
```

The pre-commit hook at `.githooks/pre-commit` blocks commits that include
paths matching `.gitignore` (catches `git add -f` slipping ephemeral state
into the repo). Bypass with `git commit --no-verify` only when you genuinely
need to commit an otherwise-ignored path.

## Build & Test

```sh
nix develop --command python3 scripts/run-tests.py   # full suite (94 tests) — MUST use nix develop
nix develop --command python3 scripts/run-tests.py --filter X  # subset
nix develop --command python3 scripts/run-tests.py --unit         # unit only
nix develop --command python3 scripts/run-tests.py --integration  # integration only
nix develop --command python3 scripts/run-tests.py --visual       # stress only
nix develop --command python3 scripts/run-tests.py --full         # all (default)
python3 .claude/scripts/lint_sty_structural.py         # structural TeX linter
python3 .claude/scripts/lint_traceability.py           # behavioral traceability check
.claude/scripts/lint-tests.sh                          # test convention linter
```

**Dev iteration**: `nix develop --command python3 scripts/run-tests.py ...` (above).
**CI / wave-close reproducibility**: `nix flake check` (runs the equivalent inside the flake build sandbox).
**Standalone stress PDF for visual review**: `scripts/build-stress-pdf.sh [SUFFIX]` (compiles all 3 variants into `pdf-out/stress-ta-<variant>[-SUFFIX].pdf` using a temp workdir with the correct TEXINPUTS layout; bypasses the runner's TEST-PDF assertions). Pair with `xdg-open` to surface PDFs for `feedback_visual_verification_required.md` review.

## Key Files

- `codependent.sty` — the package (~2500 lines)
- `codependent-render.sty` — rendering layer (~562 lines)
- `docs/PHASE3_SPEC.md` — graph redesign implementation spec (15 rounds of adversarial review)
- `docs/BEHAVIOR.md` — behavioral specification (83 testable statements with [B-XXX] IDs)
- `docs/IMPLEMENTATION_PICKUP.md` — mandatory reading gate for new agents
- `docs/CONVENTIONS.md` — coding conventions (including traceability tagging)
- `scripts/run-tests.py` — custom test runner (28 assertion types)
- `.traceability-baseline` — pre-rewrite unclassified macros/uncovered behaviors (shrinks to zero)
- `.test-behavior-baseline` — 14 tests grandfathered from `TEST-BEHAVIOR:` rule (shrinks to zero)
- `.claude/paths.toml` — single source of truth for machine-read doc paths; consult before hardcoding
- `.claude/baseline-sizes.json` — baseline ratchet; linter fails if any baseline grows
- `.latexmkrc` + `scripts/clean-build.sh` — build artifacts route to `texbuild/` + `pdf-out/`

## Directory Map

Where things go. **If your file doesn't fit here, ask before creating a new top-level dir.**

| Path | Owns | DON'T put here |
|---|---|---|
| `codependent.sty`, `codependent-render.sty` | Package source. LaTeX convention requires .sty at repo root. | Subroutines you want hidden — there's no `src/`; the .sty layer is flat. |
| `docs/` | Specs, design docs, conventions, history. Machine-read paths registered in `.claude/paths.toml`. | Scripts; build artifacts; ephemeral notes. |
| `testfiles/unit/`, `testfiles/integration/`, `testfiles/compiled-examples/` | `.lvt` fixtures + their `.tlg` siblings. NO scripts — scripts go in `scripts/`. | Scripts (those go in `scripts/`); generated outputs (those go in `testfiles/output/`). |
| `testfiles/baselines/` | Committed wire-format baseline sha256 manifests (per-wave). Plain-JSON only; raw `.aux`/`.cdp` are gitignored. | Anything hand-edited; raw build outputs; non-baseline fixtures. |
| `testfiles/output/` | Generated test artifacts (census .json, .pdf, .log). | Anything hand-edited. |
| `testfiles/support/` | Vendored support `.sty` files needed by tests (e.g. `sty-theorems-ta.sty`). | Project source; non-vendor support. |
| `testfiles/tmp/` | Truly ephemeral runner state. Safe to wipe. | Anything you want to commit. |
| `testfiles/real-world/` | Real published-paper fixtures used as fuzz/regression material. | Synthetic fixtures (those are `unit/`/`integration/`). |
| `scripts/` | Human-facing utilities + the test runner (`run-tests.py`). Invoke directly: `python3 scripts/run-tests.py` (also build cleanup, golden management). | Agent/harness tooling (that goes in `.claude/scripts/`). |
| `.claude/scripts/` | Harness/agent tooling: linters, hooks, dispatch helpers. Invoked by agents, PreToolUse hooks, and humans following CLAUDE.md. | Build/test infrastructure for end users. |
| `.claude/comms/` | Ephemeral agent communication (briefs, reports, plans). Gitignored. | Anything that should survive the session. |
| `.claude/agent_memory/` | Per-session findings/decisions. Gitignored. | Durable memory (that lives in `~/.claude/projects/...`). |
| `build/`, `texbuild/`, `pdf-out/` | Build artifacts. Gitignored. `pdf-out/goldens/` is the ONE exception that is committed. | Anything hand-authored. |
| `.githooks/` | Repo-shared git hooks (enabled via `git config core.hooksPath`). | Per-clone overrides; use `.git/hooks/` for those. |
| Repo root | Top-level config: `flake.nix`, `shell.nix`, `build.lua` (l3build), `.latexmkrc`, `.latexindent.yaml`, `CLAUDE.md`, the two `.sty` files, the three baseline files. | Scripts; docs; anything else. |

**Path-policy hook**: `.claude/scripts/pre-check-path-policy.sh` (PreToolUse on Write/Edit) warns when an agent tries to create a path outside this map. If your work genuinely needs a new top-level dir, propose it in the session and update this map first.

**Single source of truth for machine-read paths**: `.claude/paths.toml` — extend it if you add a doc that lint scripts need to find.

## Rules

- Read `docs/IMPLEMENTATION_PICKUP.md` before starting any work
- Read `docs/CONVENTIONS.md` before editing `codependent.sty`
- **All tests via `nix develop`** — PDF assertions fail without mutool/qpdf
- All tests must pass before committing — zero exceptions, zero allowlists
- Internal macros: `\codep@name`, 2-space indent, `%` at line ends
- **Every new macro must be tagged** `@behavior`, `@implements`, or `@utility` (see docs/CONVENTIONS.md)
- **Every `@behavior` tag must reference a real `docs/BEHAVIOR.md` ID**
- Use `\PackageError{codependent}` / `\PackageWarning{codependent}`, never raw TeX errors
- Credit Pavlov's dpmac (GPLv3) — see `docs/CREDITS.md`
- **Every new `.lvt` test must have `TEST-BEHAVIOR: B-X[, B-Y]` header** citing real IDs from `docs/BEHAVIOR.md` (enforced by `lint_traceability.py`). Grandfathered tests live in `.test-behavior-baseline`.
- Baselines are monotonically shrinking — `lint_traceability.py` fails if any grew. To lock in a legitimate shrinkage: `--update-ratchet`. Do NOT `--update-ratchet` to unblock a growth.
- **Manual LaTeX compiles**: use `latexmk` (reads `.latexmkrc`) or `pdflatex -output-directory=texbuild`; never leave build artifacts in the repo root. If they accumulate, run `scripts/clean-build.sh`.

## Testing policy

**Every feature must be exercised in the stress test** (`testfiles/compiled-examples/stress-ta-appendix-gray.tex`). Unit tests (`.lvt`) are necessary but NOT sufficient. The stress test is the integration ground truth — it uses real theorem styles, hyperref, cleveref, tikz-cd, concept macros, and cross-section references together. If a feature isn't in the stress test, it's not tested.

When implementing a feature:
1. Write unit tests for the specific mechanism
2. Add the feature to `stress-ta-appendix-gray.tex` with realistic usage
3. Add corresponding assertions to `testfiles/integration/trinity-test.lvt`
4. Compile the stress test and visually verify the PDF

**Do NOT declare a feature done without updating the stress test.**
