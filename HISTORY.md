# codependent.sty — Design Evolution and Audit Trail

This file documents how `codependent.sty`'s design was reached, in
chronological order, with the decisions and the failures that
preceded them. It is the navigation aid for any future agent
(human or AI) trying to understand "why is the design like this?"
or "what was tried before?" or "is X already known to break?".

For the *current* design, see `DESIGN.md`. For the *adversarial
reviews* that produced it, see `../codependent-cli/reviews/`. This
file is the connecting tissue.

## Architectural pivots (in order)

### v0.0 — Personal Pavlov-style macros (pre-2026-04)

User had a personal `\newmath` macro and ad-hoc atom-numbering
machinery in their math monograph preamble, inspired by
Pavlov's dpmac. Worked for one document, not packaged.

### v0.1 — codependent.sty as a CTAN-quality package (2026-04-08)

First commit (`941b297`). Goal: extract the personal machinery
into a reusable LaTeX package. Settled three-round adversarial
design review on the .sty layer alone (`0d66ebd`,
`tools/codependent/CONVENTIONS.md`).

Three-layer architecture proposed:

1. `codependent.sty` — atom numbering + back-ref *display*
2. External CLI — `.aux` -> `.sbr` (back-ref *computation*)
3. mwablab extension — UIDs, symbol tracking, project-specific

Rationale at the time: separation of concerns, "do one thing
well", make semantic analysis possible later via Layer 2.

### v0.2 — External Haskell CLI design (2026-04-08, `0fe7de6`)

`tools/codependent-cli/DESIGN.md` first written, 1108 lines, by
adversarial-design pod. Specified:

- Aux wire format: `\codep@atom`, `\codep@atomref`,
  `\codep@auxversion`
- Sbr wire format: `\codep@sbrversion`, `\codep@section`,
  `\codep@backref`
- FNV-1a 64 hash for staleness detection
- Haskell + megaparsec reference impl
- Lua reimplementability under ~500 lines as a portability contract

### v0.3 — REVIEW_A correctness attacks (2026-04-09, this session)

`tools/codependent-cli/reviews/REVIEW_A_correctness.md`. 15 findings.
Headline finding: **FNV-1a 64 hash is uncomputable in pdflatex**
because `\numexpr` is 31-bit signed and 64-bit unsigned multiply
is hundreds of lines of multi-word arithmetic per atom.

Other major findings: `\codep@currentatom` not cleared at atom
end (live defect), parser edge cases for `\@input`/`\newlabel`
shapes, multi-pass convergence issues.

**Triggered the architectural rethink.**

### v0.4 — REVIEW_ARCH dpmac port proposal (2026-04-09)

`tools/codependent-cli/reviews/REVIEW_ARCH_dpmac_port.md`. 1161 lines.
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

1. `codependent.sty` — numbering + non-semantic backrefs (dpmac port,
   pure TeX), writes a `.cdp` semantic-hint sidecar
2. `codependent-cli` — semantic analysis (UID tracking, concept
   graphs, `\newmath` coherence). Reads `.tex` source + `.cdp`,
   writes `concepts.json` / `uid.log` / `deps.dot`. Does NOT
   compute generic backrefs.
3. mwablab extension — project-specific work on Layer 2

The `.cdp` file is a new wire format, write-only from the .sty,
read-only by the CLI. Carries per-atom semantic metadata
(source location, labels, user `\codeptag` records,
`\newmath` declarations and uses).

### v0.6 — REVIEW_C attacks the port proposal (2026-04-09)

`tools/codependent-cli/reviews/REVIEW_C_port_proposal.md`. 14 findings.
Three BLOCKERs:

1. `\codep@extractfirst` brace parser was syntactically broken
   for cleveref's `@cref` records.
2. **`\codep@recordbr` toks-register append is O(N^2)**, not
   amortised O(1). The proposed performance estimate (~0.15s
   for 15k refs) was off by 1700x; real cost is ~253 seconds.
3. `\newlabel` override at package-load time gets clobbered
   by pre-2023 hyperref's aux-injection block.

Plus 4 MAJORs (most importantly: `\codep@currentatom` clearing
inherited from REVIEW_A finding 3) and 5 MINORs.

### v0.7 — REVIEW_D second-pass critic (2026-04-09)

`tools/codependent-cli/reviews/REVIEW_D_revision.md`. After the
proposer applied REVIEW_C's fixes, a second critic round
caught two NEW BLOCKERs introduced during the restructure:

1. **`\@setref` aux-write patch** referenced in prose but
   missing from the implementation sketch (and falsely
   claimed to be "already present in codependent.sty").
2. **`\codep@queuebackref` not wired to `\codep@collapsebr`**
   — the linked-list defer queue was built but never
   materialised into the display csname. Silent end-to-end
   pipeline break.

Plus the `\newmath` user-API signature was unspecified.

### v0.8 — Design pivot landing commit (2026-04-09, `f199852`)

`tools/codependent/DESIGN.md` grows from 518 to 2058 lines.
Adds Section 8a (dpmac port + corrected TeX sketch),
Section 8b (LaTeXML codependent.ltxml binding for hideable HTML
backrefs), Section 9a (.cdp writer with flattened record format
and end-marker sentinel). Also: `tools/codependent-cli/DESIGN.md`
rewritten from scratch as semantic-analysis-only (480 lines).
`tools/codependent/CREDITS.md` created with GPLv3 attribution
to Pavlov.

### v0.9 — Naming refinement: `\newmath` -> two macros (2026-04-09, `f4cf238`)

User flagged that `\newmath` was misleading (implies math-mode
only) and that the framework should support `\NewDocumentCommand`
in the first pass, not as a follow-up. Outcome:

- `\codepNewCommand{\Hom}[2]{...}` — wraps `\newcommand`
- `\codepNewDocumentCommand{\Cite}{s o m}{...}` — wraps
  `\NewDocumentCommand`
- Lowercase `codependent` prefix (matches existing public API),
  CamelCase suffix (mirrors LaTeX kernel definers)
- Internal `\codep@sbl@newmath` records renamed to
  `\codep@sbl@cmddef` with a `kind` discriminator
  (`newcommand` vs `NewDocumentCommand`)
- Opt-in only (no global kernel patching); migration is two
  sed lines per file
- Lua portability contract restored to CLI DESIGN.md
  (the rewrite had accidentally dropped it)

User-driven sed-safety audit: canonical token is the literal
lowercase string `codependent`; one sed pass renames everything
except the `.cdp` extension and the `sbl` substring (which
follow TeX-extension convention and intentionally stay).
Documented in CREDITS.md "Renameability" section.

### v1.0-pre — REVIEW_E package compatibility round (2026-04-09)

`tools/codependent-cli/reviews/REVIEW_E_compat.md`. 16 findings:
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
   counter. Our hook reads `\edef\codep@currentatom{\theatom}`
   and gets the atom number of an unrelated previous atom.
   Plus a duplicate `.cdp@atom` record with conflicting type.
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
catcode hazards, subfiles standalone-vs-master `.cdp` divergence.

### v1.0-test — Test fixtures + runner before implementation (2026-04-09)

After the design phase closed (commit 2e1fc2a), the user requested
test files BEFORE implementation so the implementer has concrete
TDD targets. Built in one parallel-dispatch session:

- **35 unit fixtures** under `tools/codependent/testfiles/unit/`
  covering numbering, reference recording (kernel/cleveref/hyperref/
  autoref/eqref/ref-star), KOMA/memoir/titlesec sectioning, suppression
  envs (trivlist/enumitem/tcolorbox/tikz/tikzcd), equations (separate
  + pinned-broken shared), `.cdp` writer (version/source/end-marker/
  flat-records), `\label` patching (kernel + cleveref opt-arg), the
  new public API (`\codepNewCommand`/`\codepNewDocumentCommand`/
  `\codeptag`/cmd-uses), hook & load ordering, engine matrix
  (pdflatex/lualatex), `\restatable`, `\codep@currentatom` clearing.

- **1 integration fixture** at
  `tools/codependent/testfiles/integration/test-integration-kitchen-sink.lvt`
  exercising every codependent feature in a single document with a realistic
  preamble stack (~200 lines).

- **Real-world arxiv corpus infrastructure** under
  `tools/codependent/testfiles/real-world/`: a Python `fetch.py` script
  that downloads arxiv source tarballs with SHA-256 verification, a
  `wrap.py` that injects `\usepackage{codependent}\codeptrack{...}` into
  each paper's preamble for tracked-mode compilation, a JSON
  `corpus.lock` manifest of 8 hand-curated math.* papers (3 math.CT,
  2 math.AG, 1 math.AT, 1 math.RT, 1 free) with REVIEW_E coverage
  matrix, and a README. Papers themselves are NOT committed
  (license, size); only the manifest + scripts. All SHA-256s start
  pinned to PENDING_FETCH because the dispatching agent had no
  internet access; manual verification required before first use.
  This is the smaller, fixed-corpus version of the broader
  arxiv-fuzz plan documented in
  `~/.claude/projects/.../memory/project_codependent_arxiv_fuzz.md`.

- **Test runner** at `tools/codependent/testfiles/run-tests.py`
  (~430 lines, Python 3 stdlib only). Reads machine-readable
  `%% TEST-*:` metadata headers from each `.lvt` fixture, compiles
  via pdflatex (configurable engine), reads `.aux`/`.cdp`/`.log`,
  applies assertions (exit code, log patterns, sidecar substring/
  count, atom min count), produces a per-category summary, exits
  non-zero on real failures while exempting `TEST-PINS-KNOWN-BROKEN`
  fixtures.

- **README + .gitignore** for the test suite. README documents the
  fixture format, the runner CLI, the categories, what "passing"
  means before implementation, and the system-wide texlive-full
  one-time exception (the project's Nix flake doesn't yet include
  all required packages: thmtools, scrbook, tcolorbox, tikz-cd,
  etc.; future runs should go through `nix develop` once the flake
  is updated).

**Pre-implementation TDD signal**: All 36 fixtures FAIL today
because codependent.sty v0.1 doesn't have the v1.0 features. This is
the intended state. As the implementer lands each spec section
(Section 8a, 8a.5, 8a.5.a, 8a.6, 8b, 9a), the corresponding
fixtures turn green. Implementation is "done" when the runner
reports zero real failures on all engines.

**Standalone-project framing**: The user noted that codependent.sty
is now considered its own project, only living in the mwablab
repo by historical accident. Test infrastructure is path-
independent: every script uses paths relative to
`tools/codependent/`, so a future
`git mv tools/codependent/ <new-repo>/` is a single move with
no broken paths. mwablab will eventually call codependent as a
dependency rather than embed it.

### v1.0-concept — Concept-aware forward references (2026-04-09)

After the test phase (v1.0-test, commit 031a8db) landed, the user
raised a critical practical issue with the backref architecture:
forward references. In any serious math paper, the introduction
and early sections routinely mention concepts BEFORE they are
formally defined. Auto-backref schemes that pick "first occurrence
wins" produce wrong backref graphs on ~90% of real papers. Pavlov's
manual marking was a feature, not a kludge.

Added:

- Section 8a.9 "Concept-aware forward references" (~500 lines):
  `\Hom*` starred variant inside `\codepNewCommand` marks the def
  site explicitly. New `.aux` records `\codep@concept` /
  `\codep@conceptref` feed into the existing backref pipeline via
  the `.sty`'s pass-2 rerun. New `.cdp` record `\codep@sbl@def`
  gives the CLI source-grounded concept metadata. Hybrid
  architecture (Option C): both sidecars carry the info, the `.sty`
  typeset PDF is complete without the CLI.

- §8a.5.a extended with save/clear/restore semantics on
  `\codep@currentatom` during restated theorem bodies. Nested
  restates use a counter for LIFO-safe stack. Ensures `\Hom*`
  inside a restated body NEVER registers against the enclosing
  atom's stale currentatom; only the original declaration firing
  (with alias intact) registers the def site.

- §9a `\codepNewCommand` implementation sketch updated to
  dispatch star vs non-star via `\IfBooleanTF`. Same for
  `\codepNewDocumentCommand`. Shared helpers `\codep@emit@def`
  and `\codep@emit@use` handle the concept record emissions;
  `\codep@definewrapped` factors the star-dispatch wrapping so
  both public macros share one code path.

- 5 new regression fixtures under `testfiles/unit/`:
  `test-concept-forward-ref`, `test-concept-def-site-required`,
  `test-concept-duplicate-def-site`,
  `test-concept-in-restatable-intro-teaser`,
  `test-concept-in-restatable-appendix`.

Error model:

- Missing `\Hom*` (with `\Hom` used): warning, backrefs for that
  concept disabled. No fallback to first-occurrence.
- Duplicate `\Hom*` (fired in multiple atoms): error, halts build.
- `\Hom*` with empty currentatom (inside footnote/caption or
  inside a restated body): silent no-op.

User direction: "Pavlov's manual indication of the first instance
was a feature not a kludge. Yes, there is more manual work, but
this is far better than incorrect referencing, one has to rely on
the human."

Ergonomic `^{words}` notation (Pavlov-style inline concept tagging
without requiring macro definitions) flagged as a future add-on;
deferred to v1.1+.

### v1.0 — REVIEW_E findings applied + REVIEW_F spot-check (2026-04-09)

Proposer round 3 applied all 3 BLOCKERs + 5 MAJORs + 6 MINORs
from REVIEW_E (skipping the 2 NITPICKs absorbed into BLOCKER 1
prose). DESIGN.md grew from 2208 to 3188 lines (+980).

Round 3 self-flagged 5 judgment calls and 2 residual risks for
critic verification. REVIEW_F (focused spot-check, sixth and
final adversarial round) verified all 5 judgment calls and
refuted both residual risks against actual TeX Live 2025
sources:

- **J3 (PRIMARY: label-wrap double-wrap ordering)** — VERIFIED.
  Walked cleveref.sty lines 66-97. cleveref strips the optional
  arg before forwarding to its captured target (= codependent's
  dispatcher); codependent's no-optional-arg branch fires with the
  correct mandatory key; `\codep@currentatom` is live.
- **J1 (hook-rule centralisation)** — VERIFIED.
- **J2 (`\ifx\c@theorem\c@atom` guard)** — VERIFIED against
  thm-restate.sty lines 103-184, theoremref, ntheorem.
- **J4 (trivlist suppression breadth)** — VERIFIED with caveat.
  Real blast radius from latex.ltx: `center`, `flushleft`,
  `flushright`, `verbatim`, plus amsthm envs. Acceptable for
  Pavlov-style math docs but documented in user caveats.
- **J5 (§8a.7 DeclareHookRule deduplication vs E#8 biblatex)**
  — VERIFIED.
- **R1 (`\@makechapterhead` may not exist under KOMA)** —
  REFUTED. scrbook.cls line 4132 keeps the kernel name live
  via `\@namedef{@make#1head}{\scr@makechapterhead{#1}}`.
- **R2 (test-equations-shared-align pinning)** — adequately
  documented at DESIGN.md lines 237 + 3128-3129.

REVIEW_F also surfaced 5 NITPICKs (documentation polish):
prose clarification on the J3 double-wrap mechanism,
`\@ifnextchar[` lookahead caveat, sbl/labelwrap missing
ordering rule comment, trivlist blast-radius user caveat,
and converting the R1 risk note to a "verified" note. All 5
applied in the same finishing pass before commit.

Plus one structural blip fix: `8a.6.h` summary subsection
renamed to `8a.6.m` for sequential ordering after the new
8a.6.i/j/k/l subsections from REVIEW_E.

**Design phase closed.**

### v1.1-dev — Implementation + rendering + bug fixes (2026-04-10 to 2026-04-11)

This section covers the commits between the design phase close and the
formal v1.1-impl/infra/bugs milestone entries above. The package was still
named `semtex` through most of this window; the rename to `codependent` /
`codep` prefix landed at `94d4b52`.

#### Atom numbering bugs

**Counter aliasing for thmtools `sibling=` environments** (`c6fb7b4`,
`1229274`). thmtools' `sibling=` key aliases `\c@proposition` (etc.) to
`\c@theorem` via `\let` at declaration time. When `\semtextrack` replaced
`\c@theorem` with `\c@atom`, sibling counters still pointed to the old
register, producing duplicate atom numbers (Proposition N shows the same
N as Theorem N). Two-part fix: re-`\let` every tracked env's counter
register to `\c@atom` in the `\@for` loop, and separately update `\the<env>`
to `\theatom` so the display format is also correct.

**Nested tracked environments** (`9414d2c`, `178f9bd`). A theorem-inside-
theorem fired the begin hook twice, producing a spurious inner atom record
in the `.sbl`/`.cdp` sidecar and a duplicate backref entry. Fix:
`\semtex@trackedlevel` counter; inner envs emit a `\PackageWarning` and skip
all SBL/backref writes. Counter gap from amsthm's `\refstepcounter` is
accepted by design.

**Spurious atoms for display math and `\maketitle`** (`8d8c86b`). The
paragraph begin hook fired for `equation`, `align`, `gather`, `multline`,
`flalign` (and starred variants) and also for `\maketitle`, producing atom
numbers on content that should be invisible to the tracking system. Fixed by
suppressing the hook for those environments.

**O(N²) atomlist** (`178f9bd`). The atomlist accumulator used `\xdef`
append, which copies the full list on every atom — 253 seconds for 15k
atoms. Replaced by a count-indexed csname array: O(1) per append, O(N)
walk in `\semtexappendix`.

**Base counter auto-detection** (`178f9bd`). All hardcoded `\c@theorem`
references replaced with `\semtex@basecounter`, auto-detected from the
first env in `\semtextrack`'s list.

#### Rendering: shape and font

**`\AfterEndEnvironment` for flush timing** (`c6fb7b4`). Moved
`\semtex@flushbackref` from `cmd/end<env>/before` to
`\AfterEndEnvironment` for both theorem envs and proofs, so "Used in X."
renders AFTER endmarks (QED symbols, custom theorem endmarks) rather than
before them.

**Font and size evolution** (`5241154`, `c26406a`). Initial inline renderer
let bold leak from theorem headings into the "Used in" line. Added
`\normalfont` before `\sffamily`. Size progression: `\small` →
`\footnotesize` → `\scriptsize` over three commits; `\scriptsize` won
because it makes the annotation clearly subordinate to the mathematical
content.

**Unified rendering paths** (`ce9bcc8`). Previously the theorem/env path
and the paragraph deferred path had separate formatting logic with
hardcoded fonts that couldn't be overridden. Refactored into:
`\semtex@formatusedin{reflist}` (shared text formatter, single override
point), `\semtex@renderinline{reflist}` (theorem/env), and
`\semtex@renderdeferred{reflist}` (paragraph vadjust-pre). Overriding
`\semtex@formatusedin` now changes all "Used in" output everywhere.
Added `\addvspace{\medskipamount}` after both paths to push the
annotation away from the next atom.

**Inline spacing refinement** (`a118112`). Mode detection at hook-
expansion time evaluates `\ifvmode` too early (hook fires before TeX is
in the right mode). Fix: defer detection to typesetting time via `\toks@`.
Three branches: vmode → `\noindent`; empty hmode after display math →
`\par\nobreak\noindent`; content already on line → `\unskip\hspace{0.5em}`.

#### Rendering: three styles (block, inline, margin)

**Initial block style** was the only style at the start of this window.

**Inline and margin styles** (`064220f`). Inline: flushes from
`cmd/end#1/before` (hmode, before endmark) so the "Used in" text flows on
the same line as the last content. Margin: renders in the right margin via
`\rlap`. Both styles needed follow-up fixes (see failure register below).

**`backref-color` option** (`6450bb7`). New `\semtexsetup` key; empty
value inherits surrounding colour. Inline gap tightened from `\quad` to
`\enspace`.

**`\semtexsetup` key-value API** (`25e3263`). Public configuration keys:
`backref-style` (block|inline), `backref-align` (left|right),
`backref-font`, `backref-prefix`, `backref-label`, `margin-font`. Block
mode complete; inline mode plumbed but needed further work (see failure
register).

#### Hyperref integration

**Clickable "Used in" links** (`2aff6da`). Reuses hyperref's existing
anchors from `\refstepcounter` (stored in `\newlabel` 4th field) rather
than creating separate `\hypertarget` anchors. Builds a reverse map (atom
number → anchor name) during aux read. Filters thm-restate `@data` keys to
avoid expansion errors. Labeled atoms get clickable links; unlabeled atoms
degrade gracefully to plain text.

**Auto-anchors for all atoms** (`b80a339`). Every atom (theorem, proof,
paragraph) now writes a `\semtex@anchormap` aux record mapping its display
number to its hyperref anchor name. Makes all "Used in" backrefs clickable
without requiring a `\label` on every theorem. `\newlabel`-based extraction
remains as a supplement.

**Starred hyperlink fallback** (`b80a339`). Starred backref numbers such as
"2.1*" fall back to the base theorem's anchor when the exact proof anchor is
not found, keeping proof backrefs clickable.

**Anchormap activation timing bug** (`e67d5b5`). The anchormap was activated
in `\AtBeginDocument`, which fires AFTER the aux file is read. Equation-range
anchors (e.g., `(4.4--4.5)`) written in the previous run therefore were not
loaded. Fixed by moving activation to `begindocument/before`. Also removed a
redundant duplicate definition in the `\AtBeginDocument` block.

#### Proof numbering

**Pavlov-style proof-inherits-theorem numbering** (`dd247c7`). Adjacent
proofs inherit their theorem's atom number with a `*` suffix (e.g., "2.1*").
Backrefs from inside proofs show "Used in 2.1*". Non-adjacent proofs fall
back to their own atom number with an optional warning. New SBL record
`\semtex@sbl@proof{N*}`. New `\semtex@sourceatom` mechanism for starred
backref emission. Options: `proofs=on|off`, `proof-warnings=on|off`.

**`\semtexproofof` for separated proofs** (`b974a62`). Explicitly associates
a proof appearing far from its theorem with that theorem, enabling starred
backrefs. Five tests added: separated proof, nested lemma, multiple adjacent
pairs, paragraph-breaks-adjacency, warnings-off.

#### `equations=shared` removal

The `equations=shared` option allowed multiple align lines to share one
atom number. Counter aliasing (`\c@equation → \c@atom`) caused interaction
bugs with display math suppression, producing "No counter 'v' defined"
errors (`8636a07`). The design note in `56e09ac` concluded that
equation-atom merging belongs in the CLI layer (which has full graph
visibility) rather than in the .sty. `equations=shared` was removed
(`56e09ac`); the code is trivially restorable from git history.

#### Equation backref tracking (two-track design)

**`equations=all|outer|off` modes** (`779efe4`). Two-track design for
tracking display math:

- Track 1 (single-number envs: `equation`): direct `\theequation` recording.
- Track 2 (multi-line envs: `align`, `gather`, `multline`, `flalign`): range
  `N--M` computed at environment boundaries.

Public commands: `\codeptrackeq`, `\codeptrackalign`. Default mode: `outer`.
Integration test has anti-contamination and equation assertions.

**`\ifmeasuring@` guard** (`779efe4`). amsmath runs a measuring pass through
display math to compute layout; atom-recording hooks fired during this pass,
producing phantom duplicate backref writes. Fixed with `\ifmeasuring@` guard.

#### Concept tracking and user API

**`\semtexNewCommand` → `\semtexnewcommand`** (`320f615`). Casing aligned with
`\newcommand` (lowercase). `\semtexNewDocumentCommand` kept as-is (mirrors
xparse's `\NewDocumentCommand`). Old name preserved as deprecated alias via
`\let`.

#### Backref deduplication

**Per-(source, target) dedup** (`779efe4`). Multiple patch sites firing for
the same `\cref` call (e.g., `\@setref` + `\cref@getlabel` both firing) were
writing double backref records. Fixed with per-(source,target) dedup guard.

**Concept→backref contamination removed** (`779efe4`). The concept-tracking
layer was injecting concept edges into the "Used in" lists, polluting rendered
output with concept links that belong only in the `.aux`/`.sbl` for the CLI.
Removed the injection; concepts stay in their own record type.

#### Minor adversarial review fixes (`4cd7986`)

Six items from an internal review pass:
- Flush last paragraph's deferred backref at `\AtEndDocument`
- Give `\semtex@ifdatakey` its own boolean (`\ifsemtex@isdata`)
- Guard against double `\semtextrack` call with `\PackageError`
- Remove dead code (`\semtex@build@argspec`)
- Define `\ifx` comparison constants once at load time
- Error when `\semtextrack` is called before `\newtheorem`

#### Infrastructure

**PDF content validation** (`5725aaa`). New test runner directives:
`TEST-PDF-CONTAINS`, `TEST-PDF-NOT`, `TEST-PDF-LINKS`. Uses
`mutool`/`pdftotext`/`qpdf` via subprocess; no Python library dependencies.
Skips gracefully when tools are not on PATH.

**PDF structural assertions** (`da41090`). Further directives: `TEST-PDF-STEXT`,
`TEST-PDF-STEXT-NOT`, `TEST-PDF-OBJECTS`, `TEST-PDF-OBJECTS-NOT`. Uses
`mutool stext` for text positions/fonts and `mutool show` with grep for link
annotations and destinations. `shell.nix` added providing `mupdf` + `qpdf`.

**Enriched trinity integration fixture** (`1a51109`). Exercises all 10 theorem
env types (with endmarks), restatable, tikz-cd diagrams, display math
suppression, concept tracking, cross-section backrefs, hyperref, and cleveref
in one fixture.

**`.gitignore` for build artifacts** (`b300e9d`). Aux/log/pdf/sbl files and
the stale `compiled-examples/semtex.sty` copy that caused repeated debugging
waste.

**Package rename: `semtex` → `codependent` / `codep` prefix** (`94d4b52`).
87 files, 2759 substitutions. All 60 tests pass. User-facing package name is
`codependent` (`\usepackage{codependent}`); internal macro prefix is
`\codep@`; CLI binary name is `codep`.

#### Failed approaches in this window (added to register below as items 12–16)

See the failure register section for: `\nobreak` orphan prevention (items 12,
13), `\vtop` margin rendering (item 14), `equations=shared` counter aliasing
(item 15), and inline mode hook timing via `\ifvmode` (item 16).

### v1.1-impl — Implementation phase (2026-04-10 to 2026-04-11)

Full implementation of DESIGN.md Sections 8a/8b/9a. Test suite grew
from 36 red fixtures to 68/68 green. Major implementation milestones:

- Atom numbering, theorem/proof/paragraph hooks, backref graph
- Three rendering styles: block, inline, margin
- Equation tracking: two-track design (single-number + range),
  three modes (all/outer/off)
- Concept tracking: `\codepnewcommand`, `\codepNewDocumentCommand`
- Hyperref integration: auto-anchors, starred hyperlink fallback
- Package renamed semtex → codependent (94d4b52)

Four bugs fixed: concept backref contamination, double atomref
writes, anchor collision, anchormap timing.

### v1.1-infra — Testing infrastructure + refactoring (2026-04-11)

Major infrastructure overhaul in a single session:

**Nix flake** (`064d719`). devShell with mupdf/qpdf/python3.
`nix flake check` runs the test suite. TeX Live stays system-wide.

**Integration test matrix** (`b4e9c4a`). Seven new integration tests:
integ-full-stack, integ-no-paragraphs, integ-no-hyperref,
integ-no-cleveref, integ-ntheorem, integ-equations-all,
integ-equations-off. Suite: 75/75.

**l3build framework** (`482f98c`). Standard LaTeX3 test framework
alongside the custom Python runner. 84/84 l3build, 75/75 custom.
Uses `tokens=` injection for runner compatibility, `regression-test.cfg`
for `\END` fix, `texmf.cnf` symlink for NixOS.

**PDF object-level testing** (`8c86485`). New test directives using
`qpdf --json=2`: TEST-PDF-LINK-DEST, TEST-PDF-LINK-DEST-NOT,
TEST-PDF-LINK-COUNT, TEST-PDF-DEST-EXISTS, TEST-PDF-DEST-NOT-EXISTS,
TEST-PDF-NO-ORPHAN-LINKS, TEST-PDF-LINK-RECT. Object-level
verification of hyperlink annotations, destinations, and coordinates.

**Refactoring** (5 commits). Split monolithic macros into named helpers:
`\codep@hooktheorem` (112→5 helpers), `\codep@hookproof` (76→6 helpers),
`\codep@dedupwrite` (4 duplicate sites eliminated),
`\codep@processbr`/`\codep@appendbr` unified (~30 duplicate lines),
`\codep@installparahook` flattened (5-deep→3-deep nesting).
All zero expansion overhead, 75/75 pass throughout.

**Sidecar rename** (`f56f4a2`). File extension `.sbl` → `.cdp`.
Test directives `TEST-SBL-*` → `TEST-CDP-*`. Internal macro names
`\codep@sbl@*` kept initially (renamed to `\codep@cdp@*` in v1.1-renames).

### v1.1-bugs — Bug fixes and feature additions (2026-04-11)

**Proof margin number fix** (`60c7fa6`). Removed `\global\booltrue{codep@proofpending}`
from `\codep@proof@standalone`. Proofs do NOT get margin numbers —
only paragraphs do. Design doc updated to match (was stale, incorrectly
claimed Pavlov-style proof numbering).

**`\codepproofof*` starred variant** (`2c80613`). Unstarred form:
"Used in 2.4*" links fall back to the theorem (default). Starred form:
writes an anchormap entry so the link goes to the proof location.
Use for proofs far from their theorem.

**Rendering bugs discovered** (visual PDF inspection):
1. Orphaned "Used in" across page break — investigation in progress
2. Inconsistent vertical spacing — varies by theorem style's `\topsep`
3. Phantom paragraph 2.6 — standalone proof creates atom then
   `\codepproofof` switches identity; phantom atom persists in graph

**Design decisions implemented:**
- Renamed `backref-style=block` → `below` (user-facing option)
- Changed default `backref-style` → `inline`
- Renamed `\codep@renderinline` → `\codep@renderbackref`
- Renamed `\codep@renderdeferred` → `\codep@renderbackref@para`
- Split integ-full-stack into integ-full-stack (inline) + integ-full-stack-below
- Internal macro rename `\codep@sbl@*` → `\codep@cdp@*`

### Failed approaches (v1.1-dev + v1.1-bugs session additions)

12. **`\nobreak` inside `\codep@renderbackref` for orphan prevention**
    (v1.1-bugs). The `\nobreak` and `\penalty9999` landed in horizontal
    mode (after `\leavevmode`), so they couldn't prevent vertical page
    breaks. The breakpoint is the theorem's post-spacing glue from
    `\endtrivlist`, which is in the vertical list before `\leavevmode`.

13. **`\nobreak` in `\codep@hooktheorem@afterend` before `\codep@flushbackref`**
    (v1.1-bugs). The `\nobreak` landed AFTER the theorem's post-spacing
    glue. TeX can break at glue that precedes a penalty. Sequence:
    `\addvspace{\topsep}` (breakpoint) → `\penalty10000` (too late).

14. **`\vtop` for margin rendering** (`31cc9ca`, v1.1-dev). `\vtop` is
    incompatible with LaTeX 2022+ paragraph hooks — it opens a vbox that
    the hook infrastructure doesn't expect, causing infinite recursion when
    the margin content triggered a paragraph hook. Replaced by a simple
    font group inside `\rlap` with truncation for long reflists.

15. **`equations=shared` counter aliasing** (`56e09ac`, v1.1-dev). Aliasing
    `\c@equation` to `\c@atom` to merge equation numbers with atom numbers
    caused interaction bugs with the display-math suppression code, producing
    "No counter 'v' defined" errors in `align` environments. The approach
    was abandoned; equation-atom merging requires full graph visibility and
    belongs in the CLI layer, not the .sty.

16. **`\ifvmode` for inline mode detection at hook expansion time**
    (`a118112`, v1.1-dev). The `cmd/end<env>/before` hook expands before
    TeX has committed to the mode the "Used in" text will land in. Testing
    `\ifvmode` at hook-fire time gave the wrong branch for display-math
    environments (which leave TeX in vertical mode but write the "Used in"
    into horizontal output). Fix: defer the test to typesetting time via
    `\toks@` so the three-branch dispatch (vmode / post-display hmode /
    mid-line hmode) evaluates at the correct moment.

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
- **`.cdp` extension is independent of the project name.**
  A future rename of `codependent` -> `<other>` requires a second
  sed pass to also rename `.cdp` if desired. Follows TeX
  convention (`.bbl`, `.nav`, etc.).
- **No `\providecommand` / `\renewcommand` /
  `\DeclareDocumentCommand` mirrors in v1.** The two-macro
  pair (`\codepNewCommand` + `\codepNewDocumentCommand`)
  covers the common case. Add when real use cases appear.
- **`codependent.sty` implementation is complete** (v1.1, ~2400 lines,
  75/75 tests). Refactoring and bug fixes ongoing.
- **arxiv-fuzz validation** is the planned release-gate test
  before main-merge. See
  `~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/project_codependent_arxiv_fuzz.md`
  for the harness sketch.
- **License: GPLv3.** The dpmac port creates a derivative
  work. Planned outreach to Pavlov for an optional LPPL 1.3c
  dual-license courtesy.
- **Ergonomic `^{words here}` inline notation (v1.1+)**: Pavlov's
  dpmac provides inline concept tagging via `^{words}` (in math)
  and similar forms (in text) that work without requiring the
  author to define a macro first. Syntactic sugar over the
  `\codep@concept` / `\codep@conceptref` machinery added in
  v1.0-concept (Section 8a.9). Deferred pending user feedback;
  the core concept-map infrastructure is in place so the sugar
  is a pure lexer add-on.

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
   support). Replaced by `\codepNewCommand` +
   `\codepNewDocumentCommand` pair, opt-in only.

8. **Global kernel patching** (`Option C` from the rename
   discussion, v0.9). Rejected by user as too invasive.
   "User can easily find/replace newcommands or newdoccommands."

9. **`\codep@sbl@newmath` record name** (v0.5-v0.8).
   Rejected when the user-API rename made "math" misleading.
   Replaced by `\codep@sbl@cmddef` with a `kind`
   discriminator field.

10. **Embedding kv blobs in `.cdp` records** like
    `\codep@sbl@atom{1.2.3}{paragraph}{src=foo,env=bar}`.
    Rejected by REVIEW_C finding 6 because filenames may
    contain commas. Replaced by flat one-pair-per-record
    schema.

11. **Sub-pod / nested-agent dispatch from leaf reviewers**
    (multiple checkpoint hooks fired during the session).
    Declined consistently by every leaf agent and by the
    orchestrator: harness rules forbid sub-pods, and design-
    markdown edits don't have code drift to detect.

## Cross-references

- **Current design**: `tools/codependent/DESIGN.md` (the
  living spec)
- **CLI design**: `tools/codependent-cli/DESIGN.md` (semantic-only
  Layer 2)
- **License & attribution**: `tools/codependent/CREDITS.md`
- **Adversarial reviews**: `tools/codependent-cli/reviews/`
  (REVIEW_A, REVIEW_ARCH, REVIEW_C, REVIEW_D, REVIEW_E, REVIEW_F)
- **arxiv-fuzz validation plan**:
  `~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/project_codependent_arxiv_fuzz.md`
- **Transferable lessons for other LaTeX-package projects**:
  `~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/lessons_latex_package_evolution.md`
- **Code conventions**: `tools/codependent/CONVENTIONS.md`

## How to read this file as a future agent

**If you are a FRESH ORCHESTRATOR being asked to work on
codependent.sty for the first time in a new session, STOP and read
`IMPLEMENTATION_PICKUP.md` (same directory) FIRST, then the
canonical agent-memory pickup doc at
`~/.claude/projects/-home-cornholio-Documents-research-ai-mwablab/memory/project_codependent_next_steps.md`.**
That pickup doc has the full mandatory-reading list, the
verification checkpoint, and the forbidden-actions list. This
HISTORY file is ONE of the mandatory documents but not the
only one.

If you are coming back to this project and want to:

- **Pick up the implementation phase from cold** -> read
  `IMPLEMENTATION_PICKUP.md` (top-level, same directory as
  this file) and follow its reading order. The pickup doc
  routes you through HISTORY.md + DESIGN.md + CREDITS.md +
  the six adversarial reviews + the test suite, in the right
  order, with a verification checkpoint that makes sure you
  actually absorbed the design context before editing.
- **Understand the current state** -> read `DESIGN.md`, then
  this file's "Open issues" section to know what's
  intentionally deferred.
- **Avoid repeating a known failure** -> grep the "What did
  NOT work" section (11+ items).
- **Propose a new feature** -> first check if it appears in
  the failure register, then check the open-issues list, then
  read the relevant REVIEW file from the appropriate version.
- **Understand a design decision** -> trace it back through
  the version history, then read the cited REVIEW file under
  `../codependent-cli/reviews/`.
- **Contribute lessons to other LaTeX projects** -> see the
  cross-referenced `lessons_latex_package_evolution.md` in
  user-global agent memory.
