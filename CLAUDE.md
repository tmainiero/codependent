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

## Build & Test

```sh
nix develop --command python3 testfiles/run-tests.py   # full suite (94 tests) — MUST use nix develop
nix develop --command python3 testfiles/run-tests.py --filter X  # subset
python3 .claude/scripts/lint_sty_structural.py         # structural TeX linter
python3 .claude/scripts/lint_traceability.py           # behavioral traceability check
.claude/scripts/lint-tests.sh                          # test convention linter
```

**Dev iteration**: `nix develop --command python3 testfiles/run-tests.py ...` (above).
**CI / wave-close reproducibility**: `nix flake check` (runs the equivalent inside the flake build sandbox).

## Key Files

- `codependent.sty` — the package (~2500 lines)
- `codependent-render.sty` — rendering layer (~562 lines)
- `docs/PHASE3_SPEC.md` — graph redesign implementation spec (15 rounds of adversarial review)
- `docs/BEHAVIOR.md` — behavioral specification (83 testable statements with [B-XXX] IDs)
- `docs/IMPLEMENTATION_PICKUP.md` — mandatory reading gate for new agents
- `docs/CONVENTIONS.md` — coding conventions (including traceability tagging)
- `testfiles/run-tests.py` — custom test runner (28 assertion types)
- `.traceability-baseline` — pre-rewrite unclassified macros/uncovered behaviors (shrinks to zero)
- `.test-behavior-baseline` — 14 tests grandfathered from `TEST-BEHAVIOR:` rule (shrinks to zero)
- `.claude/paths.toml` — single source of truth for machine-read doc paths; consult before hardcoding
- `.claude/baseline-sizes.json` — baseline ratchet; linter fails if any baseline grows
- `.latexmkrc` + `scripts/clean-build.sh` — build artifacts route to `texbuild/` + `pdf-out/`

## Scripts layout

- `.claude/scripts/` — harness/agent tooling: hooks, linters, dispatch helpers, wire-format checkers. Invoked by agents, PreToolUse hooks, and humans following CLAUDE.md.
- `scripts/` — repo utilities for humans (build cleanup, release scaffolding).

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
