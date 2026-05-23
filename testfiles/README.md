# codependent.sty test fixtures

This directory holds the `.lvt` fixtures and their support files. The
**test runner itself now lives at `scripts/run-tests.py`**; see its
top-of-file docstring for full usage. Quick invocations:

```sh
nix develop --command python3 scripts/run-tests.py             # full suite
nix develop --command python3 scripts/run-tests.py --filter X  # subset
nix develop --command python3 scripts/run-tests.py --unit      # unit only
nix develop --command python3 scripts/run-tests.py --integration
nix develop --command python3 scripts/run-tests.py --visual    # stress only
```

The runner exits **0 only if all real failures are zero**. Tests marked
`TEST-PINS-KNOWN-BROKEN: yes` are reported as failing in the summary
but do NOT contribute to the exit code.

## Layout

```
testfiles/
  README.md              this file (pointer; runner is in ../scripts/)
  unit/                  single-concern fixtures
    test-<category>-<name>.lvt
  integration/           full-preamble integration fixtures
  compiled-examples/     stress/visual fixtures
  real-world/            arxiv-corpus smoke test
  support/               vendored .sty / .cls files for fixtures
  output/                expected .census.json files for cdp-census checks
  tmp/                   ephemeral runner state (safe to wipe)
  test-index.md          generated fixture index (do not hand-edit)
```

The `testfiles/` root must not contain `.lvt` fixtures (rejected by the
runner). Scripts go in `scripts/`, not here.

## Fixture format

Each fixture is a `.lvt` file with two layers:

1. **Machine-readable header comment block** parsed by
   `scripts/run-tests.py` (and `scripts/test_header_parser.py`)
2. **Plain LaTeX body** (compatible with `l3build`'s `\START`/`\END`
   convention)

See `docs/CONVENTIONS.md` for the authoritative `TEST-*:` header rules
(every fixture must declare `TEST-BEHAVIOR: B-X[, B-Y]` citing
`docs/BEHAVIOR.md` IDs; grandfathered exceptions live in
`.test-behavior-baseline`).

## Cross-references

- Runner source + full usage: `scripts/run-tests.py`
- Generated fixture index: `testfiles/test-index.md`
- Header parsing shared module: `scripts/test_header_parser.py`
- Living spec: `docs/DESIGN.md`
- Project history: `docs/HISTORY.md`
