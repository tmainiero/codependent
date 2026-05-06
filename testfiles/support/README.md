# testfiles/support — vendored support files

This directory contains LaTeX support files vendored into the codependent
repo so test fixtures (especially `testfiles/compiled-examples/*.tex`)
compile in CI without depending on the developer's personal `TEXMFHOME`
or `~/texmf/` tree.

## Vendoring policy

- One copy per file. Never fork; always re-vendor by copying upstream.
- Each vendored file carries a header documenting upstream path,
  vendor date, and upstream commit hash at vendor time.
- License-compatible only: anything under LPPL 1.3c, MIT, BSD, or
  similar permissive license that allows redistribution. Files under
  GPLv3 are also acceptable since codependent itself is GPLv3.
- Update vendored files by re-copying upstream and bumping the header
  metadata. Do not edit the body in-place.

## Vendored files

| File | License | Upstream | Vendored | Used by |
|------|---------|----------|----------|---------|
| `sty-theorems-ta.sty` | LPPL 1.3c | `~/Documents/research-noai/mps/three-avatars/sty-theorems-ta.sty` (commit `14df94d`, 2025-07-29) | 2026-05-06 | `testfiles/compiled-examples/{stress-ta-*,test-ta-*}.tex` |

## Reachability

`testfiles/compiled-examples/.latexmkrc` extends `TEXINPUTS` to include
`../support` so manual `latexmk` from `compiled-examples/` finds these
files. The test runner (`testfiles/run-tests.py`) extends `TEXINPUTS`
in the per-fixture temp workspace via the same convention.

## Other files in this directory

- `regression-test.cfg`, `texmf.cnf` — TeX Live l3build harness configs
  for the existing `.lvt` test runner. Unrelated to this vendoring
  policy; do not delete.
