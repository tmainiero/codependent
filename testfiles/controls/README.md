# testfiles/controls/

Control `.tex` files for layout-parity tests.

These files compile **without** `codependent` loaded. They are paired with
integration fixtures that compile the same document structure WITH codependent
and assert byte-identical text + per-block bounding boxes (link annotations
are the only permitted difference).

## Exclusion semantics

`testfiles/controls/` is **not a fixture directory**. Files here:

- Are NOT picked up by `testfiles/unit/` or `testfiles/integration/`
  fixture discovery in `run-tests.py`.
- Are NOT scanned by `lint_traceability.py` (which only scans
  `testfiles/unit/` and `testfiles/integration/`).
- Are NOT scanned by `lint-tests.sh` (which only processes
  `testfiles/unit/*.lvt` and `testfiles/integration/*.lvt`).
- Are NOT scanned by `lint_test_kind.py` (`.tex` files outside
  `compiled-examples/` are ignored by `iter_test_fixtures`; additionally
  `controls` is in the `SKIP_DIR_NAMES` set).

Do **not** add `.lvt` files here; add them to `testfiles/unit/` or
`testfiles/integration/` instead.

## Files

| File | Paired fixture |
|------|---------------|
| `integ-appendix-layout-parity-control.tex` | `testfiles/integration/integ-appendix-layout-parity.lvt` |
| `integ-custom-headformat-doubled-control.tex` | `testfiles/integration/integ-custom-headformat-doubled.lvt` |
