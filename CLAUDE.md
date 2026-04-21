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

## Key Files

- `codependent.sty` — the package (~2500 lines)
- `codependent-render.sty` — rendering layer (~562 lines)
- `docs/PHASE3_SPEC.md` — graph redesign implementation spec (15 rounds of adversarial review)
- `docs/BEHAVIOR.md` — behavioral specification (83 testable statements with [B-XXX] IDs)
- `docs/IMPLEMENTATION_PICKUP.md` — mandatory reading gate for new agents
- `docs/CONVENTIONS.md` — coding conventions (including traceability tagging)
- `testfiles/run-tests.py` — custom test runner (28 assertion types)
- `.traceability-baseline` — pre-rewrite unclassified macros/uncovered behaviors (shrinks to zero)

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

## Testing policy

**Every feature must be exercised in the stress test** (`testfiles/compiled-examples/test-ta-style.tex`). Unit tests (`.lvt`) are necessary but NOT sufficient. The stress test is the integration ground truth — it uses real theorem styles, hyperref, cleveref, tikz-cd, concept macros, and cross-section references together. If a feature isn't in the stress test, it's not tested.

When implementing a feature:
1. Write unit tests for the specific mechanism
2. Add the feature to `test-ta-style.tex` with realistic usage
3. Add corresponding assertions to `testfiles/integration/trinity-test.lvt`
4. Compile the stress test and visually verify the PDF

**Do NOT declare a feature done without updating the stress test.**
