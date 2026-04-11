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
python3 testfiles/run-tests.py            # full suite (60 tests)
python3 testfiles/run-tests.py --filter X # subset
nix-shell                                 # dev shell with mutool, qpdf
```

## Key Files

- `codependent.sty` — the package (~2100 lines)
- `testfiles/run-tests.py` — custom test runner (not l3build)
- `testfiles/unit/*.lvt` — unit tests | `testfiles/integration/*.lvt` — integration tests
- `DESIGN.md` — living specification | `CONVENTIONS.md` — coding conventions
- `IMPLEMENTATION_PICKUP.md` — mandatory reading gate for new agents

## Rules

- Read `CONVENTIONS.md` before editing `codependent.sty`
- Read `IMPLEMENTATION_PICKUP.md` before starting any work
- All tests must pass before committing
- Internal macros: `\codep@name`, 2-space indent, `%` at line ends
- Use `\PackageError{codependent}` / `\PackageWarning{codependent}`, never raw TeX errors
- Credit Pavlov's dpmac (GPLv3) — see `CREDITS.md`

## Testing policy

**Every feature must be exercised in the stress test** (`testfiles/compiled-examples/test-ta-style.tex`). Unit tests (`.lvt`) are necessary but NOT sufficient. The stress test is the integration ground truth — it uses real theorem styles, hyperref, cleveref, tikz-cd, concept macros, and cross-section references together. If a feature isn't in the stress test, it's not tested.

When implementing a feature:
1. Write unit tests for the specific mechanism
2. Add the feature to `test-ta-style.tex` with realistic usage
3. Add corresponding assertions to `testfiles/integration/test-trinity-ta-style.lvt`
4. Compile the stress test and visually verify the PDF

**Do NOT declare a feature done without updating the stress test.**
