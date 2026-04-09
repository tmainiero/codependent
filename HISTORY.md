# semtex.sty — Design Evolution and Audit Trail

This file documents how `semtex.sty`'s design was reached, in
chronological order, with the decisions and the failures that
preceded them. It is the navigation aid for any future agent
(human or AI) trying to understand "why is the design like this?"
or "what was tried before?" or "is X already known to break?".

For the *current* design, see `DESIGN.md`. For the *adversarial
reviews* that produced it, see `../semtex-cli/reviews/`. This
file is the connecting tissue.

## Architectural pivots (in order)

### v0.0 — Personal Pavlov-style macros (pre-2026-04)

User had a personal `\newmath` macro and ad-hoc atom-numbering
machinery in their math monograph preamble, inspired by
Pavlov's dpmac. Worked for one document, not packaged.

### v0.1 — semtex.sty as a CTAN-quality package (2026-04-08)

First commit (`941b297`). Goal: extract the personal machinery
into a reusable LaTeX package. Settled three-round adversarial
design review on the .sty layer alone (`0d66ebd`,
`tools/semtex-sty/CONVENTIONS.md`).

Three-layer architecture proposed:

1. `semtex.sty` — atom numbering + back-ref *display*
2. External CLI — `.aux` -> `.sbr` (back-ref *computation*)
3. mwablab extension — UIDs, symbol tracking, project-specific

Rationale at the time: separation of concerns, "do one thing
well", make semantic analysis possible later via Layer 2.

### v0.2 — External Haskell CLI design (2026-04-08, `0fe7de6`)

`tools/semtex-cli/DESIGN.md` first written, 1108 lines, by
adversarial-design pod. Specified:

- Aux wire format: `\semtex@atom`, `\semtex@atomref`,
  `\semtex@auxversion`
- Sbr wire format: `\semtex@sbrversion`, `\semtex@section`,
  `\semtex@backref`
- FNV-1a 64 hash for staleness detection
- Haskell + megaparsec reference impl
- Lua reimplementability under ~500 lines as a portability contract

### v0.3 — REVIEW_A correctness attacks (2026-04-09, this session)

`tools/semtex-cli/reviews/REVIEW_A_correctness.md`. 15 findings.
Headline finding: **FNV-1a 64 hash is uncomputable in pdflatex**
because `\numexpr` is 31-bit signed and 64-bit unsigned multiply
is hundreds of lines of multi-word arithmetic per atom.

Other major findings: `\semtex@currentatom` not cleared at atom
end (live defect), parser edge cases for `\@input`/`\newlabel`
shapes, multi-pass convergence issues.

**Triggered the architectural rethink.**

### v0.4 — REVIEW_ARCH dpmac port proposal (2026-04-09)

`tools/semtex-cli/reviews/REVIEW_ARCH_dpmac_port.md`. 1161 lines.
Direct port analysis of Pavlov's dpmac (Plain TeX, GPLv3,
1900 lines, ~160 lines of back-ref machinery).

**Bucket catalogue:**

| Bucket | dpmac lines | Share |
|---|---|---|
| A — port verbatim | ~60 | 38% |
| B — minimal adaptation | ~35 | 22% |
| C — replaced by LaTeX primitive | ~50 | 31% |
| D — dropped | ~15 | 9% |

**Key insight**: dpmac's hand-rolled two-pass driver
(`\preprocess`, `\labelaux`, `\input\jobname` twice in one
TeX invocation) is exactly the part we DON'T need. LaTeX's
normal `.aux` rerun cycle IS dpmac's two-pass protocol, for
free. Our LaTeX port is *simpler* than the upstream Plain TeX.

### v0.5 — Refined three-layer (2026-04-09)

User clarified that the CLI should NOT die — it should refocus
on semantic analysis only. Final architecture:

1. `semtex.sty` — numbering + non-semantic backrefs (dpmac port,
   pure TeX), writes a `.sbl` semantic-hint sidecar
2. `semtex-cli` — semantic analysis (UID tracking, concept
   graphs, `\newmath` coherence). Reads `.tex` source + `.sbl`,
   writes `concepts.json` / `uid.log` / `deps.dot`. Does NOT
   compute generic backrefs.
3. mwablab extension — project-specific work on Layer 2

The `.sbl` file is a new wire format, write-only from the .sty,
read-only by the CLI. Carries per-atom semantic metadata
(source location, labels, user `\semtextag` records,
`\newmath` declarations and uses).

### v0.6 — REVIEW_C attacks the port proposal (2026-04-09)

`tools/semtex-cli/reviews/REVIEW_C_port_proposal.md`. 14 findings.
Three BLOCKERs:

1. `\semtex@extractfirst` brace parser was syntactically broken
   for cleveref's `@cref` records.
2. **`\semtex@recordbr` toks-register append is O(N^2)**, not
   amortised O(1). The proposed performance estimate (~0.15s
   for 15k refs) was off by 1700x; real cost is ~253 seconds.
3. `\newlabel` override at package-load time gets clobbered
   by pre-2023 hyperref's aux-injection block.

Plus 4 MAJORs (most importantly: `\semtex@currentatom` clearing
inherited from REVIEW_A finding 3) and 5 MINORs.

### v0.7 — REVIEW_D second-pass critic (2026-04-09)

`tools/semtex-cli/reviews/REVIEW_D_revision.md`. After the
proposer applied REVIEW_C's fixes, a second critic round
caught two NEW BLOCKERs introduced during the restructure:

1. **`\@setref` aux-write patch** referenced in prose but
   missing from the implementation sketch (and falsely
   claimed to be "already present in semtex.sty").
2. **`\semtex@queuebackref` not wired to `\semtex@collapsebr`**
   — the linked-list defer queue was built but never
   materialised into the display csname. Silent end-to-end
   pipeline break.

Plus the `\newmath` user-API signature was unspecified.

### v0.8 — Design pivot landing commit (2026-04-09, `f199852`)

`tools/semtex-sty/DESIGN.md` grows from 518 to 2058 lines.
Adds Section 8a (dpmac port + corrected TeX sketch),
Section 8b (LaTeXML semtex.ltxml binding for hideable HTML
backrefs), Section 9a (.sbl writer with flattened record format
and end-marker sentinel). Also: `tools/semtex-cli/DESIGN.md`
rewritten from scratch as semantic-analysis-only (480 lines).
`tools/semtex-sty/CREDITS.md` created with GPLv3 attribution
to Pavlov.

### v0.9 — Naming refinement: `\newmath` -> two macros (2026-04-09, `f4cf238`)

User flagged that `\newmath` was misleading (implies math-mode
only) and that the framework should support `\NewDocumentCommand`
in the first pass, not as a follow-up. Outcome:

- `\semtexNewCommand{\Hom}[2]{...}` — wraps `\newcommand`
- `\semtexNewDocumentCommand{\Cite}{s o m}{...}` — wraps
  `\NewDocumentCommand`
- Lowercase `semtex` prefix (matches existing public API),
  CamelCase suffix (mirrors LaTeX kernel definers)
- Internal `\semtex@sbl@newmath` records renamed to
  `\semtex@sbl@cmddef` with a `kind` discriminator
  (`newcommand` vs `NewDocumentCommand`)
- Opt-in only (no global kernel patching); migration is two
  sed lines per file
- Lua portability contract restored to CLI DESIGN.md
  (the rewrite had accidentally dropped it)

User-driven sed-safety audit: canonical token is the literal
lowercase string `semtex`; one sed pass renames everything
except the `.sbl` extension and the `sbl` substring (which
follow TeX-extension convention and intentionally stay).
Documented in CREDITS.md "Renameability" section.

### v1.0-pre — REVIEW_E package compatibility round (2026-04-09)

`tools/semtex-cli/reviews/REVIEW_E_compat.md`. 16 findings:
3 BLOCKERs, 5 MAJORs, 6 MINORs, 2 NITPICKs.

The critic read actual TeX Live source for every package
(thm-restate, hyperref, cleveref, titlesec, scrbook, amsthm,
amsmath, enumitem, etc.) and grounded every finding in
specific line numbers.

**Three BLOCKERs:**

1. **`\@setref` is not the universal reference dispatcher.**
   Cleveref reads `r@foo@cref` directly via `\cref@getlabel`.
   Hyperref's `\autoref` uses `\HyRef@autosetref`. `\ref*`
   uses `\real@setref` (the saved pre-patch copy). For a
   math monograph using cleveref, the back-ref graph has
   ~0% coverage. Fix: three additional patch sites at
   `cmd/begindocument/before`.

2. **`\restatable` re-fires `\AtBeginEnvironment{theorem}`**
   in a scope where `\c@theorem` has been re-let to a dummy
   counter. Our hook reads `\edef\semtex@currentatom{\theatom}`
   and gets the atom number of an unrelated previous atom.
   Plus a duplicate `.sbl@atom` record with conflicting type.
   Fix: one-line guard `\ifx\c@theorem\c@atom`.

3. **`\@startsection` wrapper is a no-op under KOMA-Script,
   memoir, titlesec.** All three replace `\@startsection`
   at load time with their own dispatchers. Section heading
   paragraphs get spuriously numbered as atoms. Fix: drop
   the wrapper, use `\AddToHook{cmd/section/before}` etc.

The MAJORs cover `\ref*` (subsumed by BLOCKER 1's fix), the
cleveref `\label[type]{key}` optional argument, `equations=shared`
mode hazards in `align`/`gather`/`\subequations`, and amsthm's
`trivlist` interaction with nested theorems.

The MINORs cover inline `\tikz`/`\tikzcd` suppression (relevant
because the user does category theory and uses `tikzcd` heavily),
`enumitem` `\newlist` registration, biblatex hook ordering,
ntheorem testing, tcolorbox/mdframed suppression, listings/minted
catcode hazards, subfiles standalone-vs-master `.sbl` divergence.

### v1.0 — Round 3 fixes incorporating REVIEW_E (in progress)

Proposer round 3 dispatched, applying all 3 BLOCKERs + 5
MAJORs + 6 MINORs (skipping the 2 NITPICKs which are absorbed
into the BLOCKER 1 prose). Adds 10 new regression test fixtures
to the testing section. Expected commit hash: TBD.

## Open issues, deferred decisions, known limitations

These are things that have been *consciously* deferred or
accepted as live limitations:

- **`\hyperref[label]{text}` is deliberately uncovered by the
  back-ref patches.** This is an author hand-rolled link, not
  a cross-reference. Documented in Section 8a.0.
- **`equations=shared` mode is best-effort.** Recommended
  default is `equations=separate`. The shared mode silently
  advances the atom counter per equation line in `align`/
  `gather`/`split`, which is rarely what the author wants.
- **Hash table saturation at 100k+ atoms.** TeX's csname hash
  table (default ~15k strings) saturates and lookup degrades.
  Users on pathological documents must increase `hash_extra`
  in `texmf.cnf`. Documented as a known limitation.
- **`.sbl` extension is independent of the project name.**
  A future rename of `semtex` -> `<other>` requires a second
  sed pass to also rename `.sbl` if desired. Follows TeX
  convention (`.bbl`, `.nav`, etc.).
- **No `\providecommand` / `\renewcommand` /
  `\DeclareDocumentCommand` mirrors in v1.** The two-macro
  pair (`\semtexNewCommand` + `\semtexNewDocumentCommand`)
  covers the common case. Add when real use cases appear.
- **`semtex.sty` itself is NOT yet modified.** All work in
  this session was design-only. Implementation of Sections
  8a / 8b / 9a is the next phase.
- **arxiv-fuzz validation** is the planned release-gate test
  before main-merge. See
  `~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/project_semtex_arxiv_fuzz.md`
  for the harness sketch.
- **License: GPLv3.** The dpmac port creates a derivative
  work. Planned outreach to Pavlov for an optional LPPL 1.3c
  dual-license courtesy.

## What did NOT work (failure register)

Things that were tried and rejected, with the reason. Future
agents should not propose these without re-litigating:

1. **External Haskell CLI for generic backrefs** (v0.2-v0.3).
   Rejected after REVIEW_ARCH showed dpmac's pure-TeX approach
   is ~60 lines of TeX vs hundreds of lines of Haskell + a
   wire format + a hash + staleness detection. The CLI now
   exists ONLY for semantic analysis, which is the real
   external-tooling use case.

2. **FNV-1a 64 staleness hash** (v0.3-v0.4). Rejected when
   REVIEW_A showed it cannot be computed in pdflatex's 31-bit
   `\numexpr`. Fix would have been `\pdfmdfivesum` (MD5 via
   pdftex primitive), but the architectural pivot to dpmac
   port eliminated the need for ANY external-tool staleness
   hash.

3. **`\@setref` as the single reference patch site** (v0.6).
   Rejected by REVIEW_E showing cleveref/hyperref bypass it
   entirely. The current design uses three patch sites
   (`\@setref`, `\cref@getlabel`, `\HyRef@autosetref` +
   `\HyRef@@StarSetRef`).

4. **`\@startsection` patching for sectioning suppression**
   (v0.1-v0.5). Rejected by REVIEW_E showing KOMA-Script,
   memoir, and titlesec all replace `\@startsection` at
   load time. Fix uses LaTeX 2021+ generic `cmd/<level>/before`
   hooks instead.

5. **Toks-register defer queue** (v0.5 sketch). Rejected by
   REVIEW_C showing `\edef\tmp{\the\toks ...}` append is
   O(N^2) — 253 seconds for 15k records. Replaced by csname
   linked list keyed by an integer counter, O(1) per append.

6. **`\newlabel` override at package-load time** (v0.5 sketch).
   Rejected by REVIEW_C showing pre-2023 hyperref's aux-file
   injection clobbers it mid-aux-read. Fix: install at
   `\AtEndPreamble` / `begindocument/before` with explicit
   `\DeclareHookRule` ordering.

7. **`\newmath{cmd}{arity}{body}` as the user-tracking macro**
   (v0.7 sketch). Rejected by user as misleading (implies
   math-mode-only) and incomplete (no `\NewDocumentCommand`
   support). Replaced by `\semtexNewCommand` +
   `\semtexNewDocumentCommand` pair, opt-in only.

8. **Global kernel patching** (`Option C` from the rename
   discussion, v0.9). Rejected by user as too invasive.
   "User can easily find/replace newcommands or newdoccommands."

9. **`\semtex@sbl@newmath` record name** (v0.5-v0.8).
   Rejected when the user-API rename made "math" misleading.
   Replaced by `\semtex@sbl@cmddef` with a `kind`
   discriminator field.

10. **Embedding kv blobs in `.sbl` records** like
    `\semtex@sbl@atom{1.2.3}{paragraph}{src=foo,env=bar}`.
    Rejected by REVIEW_C finding 6 because filenames may
    contain commas. Replaced by flat one-pair-per-record
    schema.

11. **Sub-pod / nested-agent dispatch from leaf reviewers**
    (multiple checkpoint hooks fired during the session).
    Declined consistently by every leaf agent and by the
    orchestrator: harness rules forbid sub-pods, and design-
    markdown edits don't have code drift to detect.

## Cross-references

- **Current design**: `tools/semtex-sty/DESIGN.md` (the
  living spec)
- **CLI design**: `tools/semtex-cli/DESIGN.md` (semantic-only
  Layer 2)
- **License & attribution**: `tools/semtex-sty/CREDITS.md`
- **Adversarial reviews**: `tools/semtex-cli/reviews/`
  (REVIEW_A, REVIEW_ARCH, REVIEW_C, REVIEW_D, REVIEW_E)
- **arxiv-fuzz validation plan**:
  `~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/project_semtex_arxiv_fuzz.md`
- **Transferable lessons for other LaTeX-package projects**:
  `~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/lessons_latex_package_evolution.md`
- **Code conventions**: `tools/semtex-sty/CONVENTIONS.md`

## How to read this file as a future agent

If you are coming back to this project and want to:

- **Understand the current state** -> read `DESIGN.md`, then
  this file's "Open issues" section to know what's
  intentionally deferred.
- **Avoid repeating a known failure** -> grep the "What did
  NOT work" section.
- **Propose a new feature** -> first check if it appears in
  the failure register, then check the open-issues list, then
  read the relevant REVIEW file from the appropriate version.
- **Understand a design decision** -> trace it back through
  the version history, then read the cited REVIEW file.
- **Contribute lessons to other LaTeX projects** -> see the
  cross-referenced `lessons_latex_package_evolution.md`.
