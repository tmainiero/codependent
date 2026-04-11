# real-world/ — arxiv corpus for codependent.sty integration smoke tests

This directory is a **fixed, hand-curated** corpus of real arxiv math
papers used to smoke-test `codependent.sty` against actual-in-the-wild
LaTeX. It is the small, committed companion to the larger
**arxiv-fuzz** validation plan (~100 papers, post-implementation,
random sample) documented in:

```
~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/\
memory/project_codependent_arxiv_fuzz.md
```

Whereas the fuzz run is random-sampled and thrown away, the corpus
under `real-world/` is **version-pinned**, **sha-verified**, and
**regression-stable** across releases.

## What lives here

| File | Purpose | Committed? |
|---|---|---|
| `corpus.lock` | Manifest: arxiv IDs, versions, sha256s, per-paper notes | yes |
| `fetch.py` | Downloads tarballs per manifest, verifies sha, extracts | yes |
| `wrap.py` | Generates `wrappers/<id>.tex` from a downloaded paper | yes |
| `README.md` | This file | yes |
| `.gitignore` | Excludes `papers/` and `wrappers/` | yes |
| `papers/<id>/` | Extracted source trees (fetched on demand) | **no** |
| `wrappers/<id>.tex` | Codependent-injecting wrappers around each paper | **no** |

Fetched paper contents and generated wrappers are deliberately NOT
committed. Only the manifest and the logic to reconstruct them live
in git.

## License note

Arxiv source tarballs are publicly available, but **every paper
carries its own license** (arxiv's default non-exclusive license,
CC-BY, CC-BY-SA, or an author-specific variant). Because we do not
own and cannot relicense those contents, `papers/` is gitignored and
this repository ships only:

- the manifest (factual reference to publicly-archived URLs),
- our scripts,
- this README.

If you add a paper to the corpus that you believe should be shipped
with the repo as a test fixture, first check its license at
`https://arxiv.org/abs/<id>` and confirm it permits redistribution.

## Arxiv "be nice" policy

Arxiv asks automated clients to stay under **4 requests per second**
and to **fetch sparingly**. Our `fetch.py`:

- sleeps 300 ms between downloads (~3.3 req/s worst case),
- sends a descriptive `User-Agent: codependent test corpus / codependent-arxiv-corpus 0.1`,
- is idempotent (already-fetched papers are skipped on rerun).

**Do not** run `fetch.py` in CI loops. Treat it as a once-per-release
operation performed by a developer on a dev machine.

## Quickstart

From this directory (or any ancestor):

```bash
# 1. Inspect the manifest.
python fetch.py --list

# 2. Fetch everything into papers/.
python fetch.py

# 3. Generate wrappers/<id>.tex for every paper.
python wrap.py --all

# 4. (Future) Run the main test harness; it will look for
#    wrappers/*.tex and compile each one with pdflatex.
```

## First-use sha population

The manifest ships with `sha256: PENDING_FETCH` for every paper
because no agent in the creation dispatch had internet access to
actually verify IDs or compute hashes. **Before the corpus is
usable, a human (or a WebFetch-capable agent) must populate the
shas.** Procedure per paper:

```bash
# 1. Verify the arxiv ID actually exists and matches the title
#    recorded in corpus.lock. Browse https://arxiv.org/abs/<id>.
#
# 2. Fetch with pending-acceptance; the observed sha prints to
#    stderr.
python fetch.py --accept-pending <id>
#
# 3. Edit corpus.lock and replace PENDING_FETCH for that entry
#    with the printed sha.
#
# 4. Re-run without --accept-pending to confirm the sha matches.
python fetch.py <id>
```

Once every entry has a real sha, commit `corpus.lock` and the
corpus is frozen.

## Integration with the main test runner

The top-level test harness is expected to:

1. (Precondition, manual) run `python fetch.py && python wrap.py --all`
2. Iterate over `wrappers/*.tex`.
3. For each wrapper, run `pdflatex -interaction=nonstopmode <id>.tex`
   **twice** (the dpmac port requires a rerun for backref population).
4. Collect per-paper metrics:
   - pdflatex exit code,
   - presence of `\codep@sbl@end{OK}` sentinel in the generated
     `.sbl` file,
   - atom-count stability between the two passes,
   - log lines matching `Warning|Error|codependent`.
5. Triage any failure into a regression fixture under
   `testfiles/integration/` (extracted minimal repro) and move on.

The runner does not need to understand arxiv metadata; everything
it needs is in `wrappers/*.tex`.

## Selection criteria (how papers were chosen)

Each of the ~8 papers in `corpus.lock` targets one or more of the
predicted breakage surfaces from REVIEW_E_compat:

- **BLOCKER E#1 (cleveref back-ref patch coverage)**: at least two
  heavy `\cref`/`\Cref` users.
- **BLOCKER E#2 (`\restatable` hook double-fire)**: one candidate
  marked RARE (the `thmtools`/`\restatable` pattern is genuinely
  uncommon in practice; if the candidate paper turns out not to use
  it, replace with a hand-crafted regression fixture).
- **BLOCKER E#3 (`\@startsection` no-op under KOMA/memoir/titlesec)**:
  one KOMA-Script candidate.
- **MAJOR (`equations=shared` hazard)**: one heavy `align`/`gather`
  user.
- **MINOR (tikzcd inline suppression)**: one tikzcd-heavy paper —
  aligned with the user's own heavy tikzcd use in their monograph.
- **Length diversity**: one paper <10 pages (short-doc smoke path),
  one paper 50+ pages (long-doc stress).
- **Cross-reference density**: at least one paper with 10+ `\ref`s
  to stress the backref pipeline.

Categories covered: `math.CT` (x3), `math.AG` (x2), `math.AT`,
`math.RT`, plus free-choice slots. See `corpus.lock`'s
`coverage_matrix` field for the exact mapping.

## Relationship to other test directories

| Directory | Purpose |
|---|---|
| `testfiles/unit/` | Unit tests (`l3build` check), per-feature |
| `testfiles/integration/` | Integration tests against hand-crafted fixtures |
| `testfiles/real-world/` | **This dir** — smoke tests against real arxiv papers |
| `testfiles/arxiv-regression/` | (Future) Regression fixtures extracted from fuzz failures |

## Troubleshooting

**`ERROR: paper X has sha256=PENDING_FETCH`**
Populate the sha (see "First-use sha population" above).

**Rate-limited / HTTP 503 from arxiv**
Wait 5 minutes, then rerun. `fetch.py` is idempotent and will
only retry the papers that did not land.

**`wrap.py` says "no .tex file found"**
The paper may be a PDF-only arxiv submission. Remove it from
`corpus.lock` and pick a source-available replacement.

**`wrap.py` says "already loads codependent in preamble"**
Someone added a paper that already uses codependent (extremely unlikely
before v1.0). Check the paper and replace the entry.

## Forward-compat note (moving to a separate repo)

Per the three-layer architecture plan, `tools/codependent/` is
intended to be extracted into a standalone CTAN repo later. This
directory uses **only relative paths and `Path(__file__).parent`**
so the scripts will work unchanged after extraction.
