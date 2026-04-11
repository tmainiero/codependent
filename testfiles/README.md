# codependent.sty test suite

Test fixtures and runner for `codependent.sty`. Designed to be useful
**before the implementation lands** — the assertions target
observable artifacts (`.aux`, `.sbl`, `.log`, exit code) so an
implementer running these tests in red-green-refactor mode has
concrete TDD targets without needing pre-locked golden files.

`codependent.sty` is a standalone CTAN-targeted package. It currently
lives under `tools/codependent/` inside the `mwablab` repository
for historical reasons; it will eventually split into its own
repo. The test suite is **path-independent**: every script uses
relative paths from `tools/codependent/`, so a future
`git mv tools/codependent/ <new-repo>/` is a single move.

## Layout

```
testfiles/
  README.md              this file
  run-tests.py           the test runner (Python 3, stdlib only)
  unit/                  ~30 single-concern fixtures
    test-<category>-<name>.lvt
  integration/           ~5 realistic-preamble integration fixtures
  real-world/            arxiv-corpus smoke test
    fetch.py             arxiv tarball downloader
    wrap.py              wrapper-generation script
    corpus.lock          paper manifest with SHA-256 pins
    .gitignore           papers/ and wrappers/ NOT committed
    README.md            real-world subdir docs
  test-*.lvt             v0.1 stub fixtures (legacy, not run by run-tests.py)
```

The `testfiles/` root contains 11 stub `.lvt` files from the
v0.1 design. They are kept for historical reference and as
seed material for the implementer; the modern runner only
discovers `unit/*.lvt` and `integration/*.lvt`.

## Running

```sh
# Run everything (unit + integration). Uses pdflatex by default.
python3 run-tests.py

# Subset by regex.
python3 run-tests.py --filter cleveref
python3 run-tests.py --filter "^test-section-"

# Just unit, just integration, or include real-world arxiv corpus.
python3 run-tests.py --unit-only
python3 run-tests.py --integration-only
python3 run-tests.py --real-world

# Engine matrix.
python3 run-tests.py --engine pdflatex   # default
python3 run-tests.py --engine lualatex
python3 run-tests.py --engine xelatex

# Inspect a failing test's working directory.
python3 run-tests.py --filter test-restatable-single --keep-temp -v
# -> testfiles/tmp/test-restatable-single/  contains the .aux, .sbl, .log
```

The runner exits **0 only if all real failures are zero**.
Tests marked `TEST-PINS-KNOWN-BROKEN: yes` are reported as
failing in the summary but do NOT contribute to the exit code
(they intentionally pin hazards documented in the design).

## Fixture format

Each fixture is a `.lvt` file with two layers:

1. **Machine-readable header comment block** parsed by `run-tests.py`
2. **Plain LaTeX body** (compatible with `l3build`'s `\START`/`\END`
   convention; `l3build` can adopt these fixtures later when golden
   `.tlg` files exist)

### Header keys (all `%% TEST-*:` prefix)

| Key | Cardinality | Meaning |
|---|---|---|
| `TEST-NAME` | 1 | matches the filename without `.lvt` |
| `TEST-WHAT` | 1 | one-sentence "what is being tested" |
| `TEST-SOURCE` | 1 | which REVIEW finding or DESIGN.md section motivated this test |
| `TEST-SECTION` | 1 | DESIGN.md cross-reference |
| `TEST-EXIT` | 1 | expected `pdflatex` exit code (almost always `0`) |
| `TEST-LOG-NOT` | * | regex pattern that must NOT appear in `.log` |
| `TEST-LOG-CONTAINS` | * | regex pattern that MUST appear in `.log` |
| `TEST-SBL-CONTAINS` | * | substring that MUST appear in `.sbl` |
| `TEST-SBL-NOT-CONTAINS` | * | substring that must NOT appear in `.sbl` |
| `TEST-SBL-COUNT` | * | `<substring> = <n>` count assertion |
| `TEST-SBL-LAST-RECORD` | 1 | substring that MUST appear in the LAST non-empty line of `.sbl` (stronger than `CONTAINS`; used to pin the end-marker sentinel position) |
| `TEST-AUX-CONTAINS` | * | substring that MUST appear in `.aux` |
| `TEST-AUX-NOT-CONTAINS` | * | substring that must NOT appear in `.aux` |
| `TEST-ATOMS-MIN` | 1 | minimum count of `\codep@sbl@atom{` records |
| `TEST-PACKAGES` | 1 | comma-separated list of packages this fixture loads |
| `TEST-RERUN` | 1 | number of `pdflatex` passes (default 2 for backref population) |
| `TEST-PINS-KNOWN-BROKEN` | 1 | `yes` marks intentional hazard pin (exempted from exit code) |

Repeating keys may appear multiple times in the header.

### Example

```latex
%% TEST-NAME: test-setref-cleveref
%% TEST-WHAT: Verify \cref{thm:A} produces a backref edge in .sbl.
%% TEST-SOURCE: REVIEW_E #2 (BLOCKER)
%% TEST-SECTION: DESIGN.md §8a.0
%% TEST-EXIT: 0
%% TEST-LOG-NOT: codependent.*Error
%% TEST-SBL-CONTAINS: \codep@sbl@end{OK}
%% TEST-AUX-CONTAINS: \codep@atomref{1.2}{thm:A}
%% TEST-PACKAGES: hyperref,cleveref,amsthm,codependent
%% TEST-RERUN: 2
%%
%% Plain-English explanation of what this test catches and why...

\documentclass{article}
\usepackage{hyperref}
\usepackage{cleveref}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\usepackage{codependent}
\codeptrack{theorem}

\begin{document}
\START

\begin{theorem}\label{thm:A}First.\end{theorem}
\begin{theorem}By \cref{thm:A}, second.\end{theorem}

\END
\end{document}
```

## TeX distribution

For the design/test phase (2026-04-09 onward), the runner uses
the **system-wide** `texlive-full` because the project's Nix
flake does not yet include all required packages (`thmtools`,
`scrbook`, `tcolorbox`, `tikz-cd`, etc.). The runner detects
the system `pdflatex`/`lualatex` at startup and prints a
notice.

This is a **one-time exception** documented in
`tools/codependent/HISTORY.md`. Future runs (post-implementation,
after the Nix flake is updated) should go through `nix develop`.

## Categories

### `unit/` — single-concern fixtures (~30)

Each unit fixture isolates exactly one feature so a regression
points at a specific spec section. Categories:

- **Numbering**: basic atom counter, depth=1/2/3 display formats
- **Reference recording**: kernel `\ref`, `\cref`, `\autoref`,
  `\ref*`, `\eqref` — REVIEW_E #1 BLOCKER coverage
- **Sectioning**: article, KOMA, memoir, titlesec —
  REVIEW_E #5 BLOCKER coverage
- **Suppression**: trivlist, enumitem newlist, tcolorbox,
  tikz, tikzcd
- **Equations**: separate (default), shared (pinned-broken)
- **Sidecar `.sbl`**: header records, end marker, flat records
- **`\label` patching**: kernel and cleveref optional-arg forms
- **New public API**: `\codepNewCommand`,
  `\codepNewDocumentCommand`, `\codeptag`, command uses
- **Hook & load ordering**: codependent before/after
  hyperref/cleveref
- **`\restatable`**: REVIEW_E #2 BLOCKER coverage
- **`\codep@currentatom` clearing**: REVIEW_A #3 LIVE DEFECT
- **Engine matrix**: pdflatex, lualatex (xelatex deferred)

### `integration/` — kitchen-sink + realistic preambles (~5)

Each integration fixture exercises many features in one
document, mimicking a realistic mathematical preamble.

- **`test-integration-kitchen-sink.lvt`** — every common
  package + every codependent feature in one document
- (additional realistic preambles to be added)

### `real-world/` — actual arxiv papers

A small fixed corpus (~5-10 hand-curated `math.*` papers
from arxiv) used as integration smoke tests. Papers are
NOT committed to the repo (license, size); only the
manifest, fetch script, and wrapper-generation logic are.

See `real-world/README.md` for fetch + wrap procedures.

This is the smoke version of the broader arxiv-fuzz plan
(see `~/.claude/projects/.../memory/project_codependent_arxiv_fuzz.md`):
~5-10 papers as a fixed regression corpus, ~100-1000
papers as the periodic full fuzz before main-merge.

## What "passing" means before implementation

`codependent.sty` is currently the v0.1 stub (654 lines). The
v1.0 implementation has not yet been written. **All
fixtures will fail when run today** because the v0.1 stub
does not implement:

- The dpmac-port backref machinery (Section 8a)
- The `.sbl` writer (Section 9a)
- The new public API (`\codepNewCommand`,
  `\codepNewDocumentCommand`, `\codeptag`)
- The cleveref/hyperref reference patches (Section 8a.0)
- The `\@startsection` → `cmd/section/before` migration
  (Section 8a.6.i)
- The currentatom clearing fix (Section 8a.5)
- The `\restatable` guard (Section 8a.5.a)

That is the intended state. As the implementer lands each
spec section, the corresponding fixtures turn green. The
implementation is "done" when the runner reports zero real
failures (excluding pinned-broken hazards) on all three
engines (pdflatex, lualatex, xelatex).

## Cross-references

- **Living spec**: `tools/codependent/DESIGN.md`
- **Project history**: `tools/codependent/HISTORY.md`
- **Audit trail**: `tools/codependent-cli/reviews/` (six rounds)
- **Transferable lessons**: see `MEMORY.md` for the pointer
  to `lessons_latex_package_evolution.md` in user-global
  agent memory
