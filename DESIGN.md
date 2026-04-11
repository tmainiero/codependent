# codependent.sty Design

LaTeX package for Pavlov-style automatic atom numbering and
back-reference display.  **The back-reference machinery is a
direct port of Dmitri Pavlov's
[dpmac](https://dmitripavlov.org/tex/dpmac.tex) (Plain TeX, GNU
GPLv3, 2007-2023)** into the LaTeX2e hook system.  Zero external
tooling is required for the back-reference-display use case:
graph inversion happens inside pdflatex on pass 2.

This architecture was settled after three rounds of adversarial
review (see `tools/codependent-cli/reviews/`).  An earlier design
delegated graph inversion to an external Haskell CLI via a
`.sbr` sidecar; that design has been **superseded**.  The new
architecture is three-layered:

| Layer | Tooling | Role |
|---|---|---|
| 1. `codependent.sty` | pure TeX, GPLv3 | Numbering + generic back-refs (this file) |
| 2. `codependent-cli` | Haskell (future) | **Semantic** analysis only (UIDs, deps, concepts) |
| 3. mwablab ext. | project-specific | Builds on Layer 2 |

Layers 1 and 2 communicate one-way: the `.sty` writes a
`.sbl` semantic-hint sidecar (Section 9a); the CLI reads it
and never writes anything the `.sty` reads back.  The only
two-way persistence is LaTeX's own `.aux` file.

## Separation of concerns

The codependent ecosystem has three layers.  The `.sty` is the
bottom layer — it knows nothing about the layers above.

| Layer | What | Audience |
|---|---|---|
| **codependent.sty** | Atom numbering + generic back-ref display (pure TeX, dpmac port) | Anyone (CTAN) |
| **codependent-cli** | Semantic analysis: `.tex` + `.sbl` -> concept/UID/dep outputs | Anyone using the `.sty` for structured docs |
| **mwablab extension** | Project-specific semantic tooling on top of the CLI | Project-specific |

The `.sty` is fully standalone for the back-reference-display
use case.  It computes the back-reference graph in pure TeX
(see Section 8a) via a direct port of the relevant macros from
Dmitri Pavlov's `dpmac.tex`, and it writes a companion
semantic-hint sidecar file (`.sbl`, see Section 9a) that the
CLI reads for purely semantic work.  The CLI is **not** in
the back-reference-display pipeline at all.

## Architecture

```
pdflatex main.tex          pass 1: .sty numbers atoms, writes .aux + .sbl
pdflatex main.tex          pass 2: .sty reads .aux, inverts the ref graph
                                   in TeX, appends "Used in X, Y." per atom
codependent-cli analyse main.tex optional: reads .tex + .sbl (+ .aux), writes
                                      semantic-analysis artifacts
```

The two pdflatex runs are LaTeX's ordinary rerun cycle.  No
external tool is involved for back-ref display.  On pass 1,
the `.aux` has no `\codep@atomref` records from a previous
run (or only stale ones), so the flushed back-ref queue is
empty and nothing is rendered.  On pass 2 the `.aux` is
populated and the "Used in" lines appear.  A single-pass
build produces a correctly numbered document — just without
back-references.  This matches how `\ref`, `toc`, and
`\pageref` all work, and users are trained for it.

For multi-file projects using `\subfiles` or `\include`, a
master document (`main.tex`) is required for the canonical
build.  Individual subfiles can still be compiled standalone
for drafting — they get local numbering (1.1, 1.2, ...) which
is correct within that file but not globally unique.

## Load order

```latex
\usepackage{amsthm}          % or ntheorem — load first
\newtheorem{theorem}{...}[section]
\newtheorem{definition}[theorem]{Definition}
...                           % all \newtheorem declarations
\usepackage{codependent}          % after all \newtheorem
\codeptrack{definition,theorem,proposition,...}
```

codependent.sty loads AFTER the theorem backend and AFTER all
`\newtheorem` declarations.  `\codeptrack{...}` performs
post-hoc aliasing of the shared theorem counter to the `atom`
counter.  It also auto-registers starred variants (e.g.,
`definition` → both `definition` and `definition*`, which
`amsthm` creates automatically).

## Numbering

### Shared counter

One counter (`atom`) for all block types: paragraphs,
definitions, theorems, propositions, lemmas, corollaries,
remarks, examples, proofs.

When `\codeptrack` is called, it:

1. Creates the `atom` counter.
2. Copies the current value of the `theorem` counter to
   `atom` (preserving any state).
3. Aliases `theorem` to `atom`
   (`\let\c@theorem\c@atom`).
4. Updates counter reset lists: removes `theorem` from
   the `section` counter's reset list (from
   `\newtheorem`'s `[section]` argument) and adds `atom`
   to the reset list of the appropriate sectioning level
   (determined by the `depth` option).  Uses
   `\@removefromreset` and `\@addtoreset`.
5. Updates the display format (`\theatom`) to match the
   depth setting.

All `\newtheorem` definitions that shared the `theorem`
counter now share the `atom` counter via the alias.
Existing `\label`/`\ref` pairs continue to work because
`\c@theorem` points to the same register as `\c@atom`.

Because `\newtheorem` already advances the counter on entry
(via the alias), the `\AtBeginEnvironment` hook does NOT
advance it again — it only handles suppression and display
formatting.  No double-increment.

### Depth

The `depth` option controls how many sectioning levels appear
in the atom number and where the counter resets:

```latex
\usepackage[depth=1]{codependent}  % 2.3      (default)
\usepackage[depth=2]{codependent}  % 2.1.3
\usepackage[depth=3]{codependent}  % 2.1.3.4  (if you must)
```

Depth is relative to the document's top-level sectioning
command.  The `.sty` auto-detects whether `\chapter` exists
(book/report) or not (article):

| depth | article | book/report |
|---|---|---|
| 1 | section.atom | chapter.atom |
| 2 | section.subsection.atom | chapter.section.atom |
| 3 | section.sub.subsub.atom | chapter.section.sub.atom |

The atom counter resets at the deepest sectioning level
included in the display number.  Any existing counter reset
from `\newtheorem`'s `[section]` argument is harmless — the
atom counter is the same counter, and resetting at a coarser
level is a subset of resetting at a finer level.

### Equation numbering

Equation numbering is always independent of atom numbering.
Atoms use the `atom` counter (margin superscripts); equations
use the standard `equation` counter (parenthesized numbers).
The old `equations=shared` mode (counter aliasing) was removed
— it had intractable hazards with `align`/`gather`/`subequations`
(see REVIEW_E #6).

### Equations as backref sources

Equations can appear as sources in "Used in" lists.  When
`\ref{thm:main}` appears inside a numbered equation, the
equation number is recorded as the backref source, displayed
with parentheses to distinguish from atom numbers:

```
Used in 2.1, (3), (5--7).
           ^    ^       ^
       theorem  eq    align range
```

The parenthesized form serves as both display format (standard
math convention) and internal namespace key (prevents collision
between theorem 4.1 and equation 4.1 in the anchormap and
backref data structures).

#### Three modes

```latex
\codepsetup{equations=outer}  % default
\codepsetup{equations=all}
\codepsetup{equations=off}
```

| Mode | Behaviour |
|------|-----------|
| `outer` | Equations outside theorems/proofs are backref sources. Equations inside a tracked environment fall through to the containing atom (theorem/proof number). |
| `all` | Every numbered equation is a backref source, even inside theorems. May produce both "2.1" and "(3)" in the same "Used in" list. |
| `off` | Equations never appear as sources. Refs inside equations are attributed to the containing atom, or silently dropped if no containing atom exists (e.g. `paragraphs=off`). |

**Default is `outer`.**  This is the least surprising: standalone
equations (between theorems, in running text) get tracked — important
because with `paragraphs=off` these refs would otherwise be lost
entirely.  Equations inside theorems fall through to the theorem
number, avoiding "(3)" alongside "2.1" in the same list.

#### Two-track implementation

Equation environments are semantically two kinds: single-number
(one equation counter step) and multi-number (one step per line).
amsmath steps the counter at different points for each kind —
at `\begin` for single-number, at `\\` (after line content) for
multi-number.  These require different recording strategies.

##### Track 1: Single-number environments (`equation`)

`\refstepcounter{equation}` fires at `\begin{equation}`, BEFORE
content.  At `\ref` time, `\theequation` is correct.

Record `(\theequation)` as backref source directly in
`\codep@writeatomref`.  Write anchormap entry lazily at
`\ref` time.

##### Track 2: Multi-number environments (`align`, `gather`, `multline`, `flalign`)

`\refstepcounter{equation}` fires at `\\` (end of row), AFTER
line content.  At `\ref` time, `\theequation` is stale
(off by one).  Reading `\theequation` at `\ref` time produces
wrong source numbers.

**Note:** `multline` is Track 2 despite having a single equation
number — its counter also steps late (via `\make@display@tag`),
not at `\begin{multline}`.

**Range-based recording.**  Instead of tracking per-line equation
numbers, attribute all `\ref`s in the block to the block's
equation range:

1. At `\begin{align}`: save `\c@equation` (raw counter value).
   Inject a dedicated `\hypertarget` anchor for the block
   (do NOT rely on `\@currentHref`, which at `\end{align}`
   points to the last row's anchor or is stale if all rows
   have `\notag`).
2. During content: any `\ref` → append the target label key
   to a pending list.  Do NOT capture `\theequation` — it is
   wrong at this point.  Guard the append with `\ifmeasuring@`
   to skip amsmath's measuring pass (which fires `\ref` twice).
3. At `\end{align}`: compute the formatted range:
   ```latex
   \begingroup
     \c@equation=\codep@eq@startcount\relax
     \advance\c@equation by 1\relax
     \edef\codep@eq@startdisplay{\theequation}%
   \endgroup
   \edef\codep@eq@enddisplay{\theequation}
   ```
   If start == end (single numbered line, or `multline`):
   display `(N)`.  If start < end: display `(N--M)`.  If
   counter did not advance (all `\notag`): fall through to
   containing atom, or silently drop if no containing atom.
4. Write `\codep@atomref{(N--M)}{target}` for each pending ref.
   Write `\codep@writeanchormap{(N--M)}` using the dedicated
   anchor from step 1.
5. Clear the pending list.

**Internal key format.**  Use ASCII `--` (two hyphens) as the
range separator in csname keys: `codep@anchor@(2--4)`.  Render
as en-dash (`\textendash`) only at display time in
`\codep@brhyper`.  ASCII hyphens are catcode 12 on all engines
(pdfLaTeX, LuaLaTeX, XeLaTeX) and survive aux file
round-tripping.  The display key and the internal key are NOT
the same string — `\codep@brhyper` maps `--` to `\textendash`
for rendering.

**Registration.**  Two internal registration commands:

- `\codep@trackeqenv{env}` — Track 1 (single-number, direct)
- `\codep@trackalignenv{env}` — Track 2 (multi-number, range)

Public commands for custom environments:

- `\codeptrackeq{env}` — register as Track 1
- `\codeptrackalign{env}` — register as Track 2

Starred/unnumbered environments (`equation*`, `align*`, etc.)
use the existing `\codep@suppressenv` — paragraph suppression
only, no equation tracking.

#### Pre-requisite: atomref dedup bug fix

Before implementing equation tracking, fix two existing bugs
that produce duplicate/disordered "Used in" entries:

1. **Multiple patch sites fire for one `\cref` call.**
   `\cref{thm:main}` triggers both `\cref@getlabel` (patch 2)
   and `\@setref` (patch 1), each writing an `\codep@atomref`
   record.  Fix: add per-source-target dedup in
   `\codep@writeatomref@do` — one aux write per (source, target)
   pair per compile pass.

2. **amsmath measuring pass fires `\ref` twice.**  amsmath
   processes `align`/`gather`/`multline`/`flalign` bodies twice
   (measuring + typesetting).  `\ref` fires both times.
   `\protected@write` in the measuring box is discarded, but
   global state (like dedup marks) persists.  Fix: guard
   `\codep@writeatomref` with `\ifmeasuring@` (skip entirely
   during the measuring pass).

Both fixes use only documented interfaces (`\ifmeasuring@` is
a public amsmath conditional).  The `\ifmeasuring@` guard must
come BEFORE the dedup marks to avoid setting marks during the
measuring pass that would block the real (typesetting) pass.

#### Design decisions and alternatives considered

1. **Why two tracks instead of one mechanism?**  `equation` and
   `align` are semantically different: a single equation vs a
   multi-line derivation.  amsmath steps the counter at different
   points for each.  Forcing one mechanism produces either
   incorrect numbers (reading `\theequation` at `\ref` time in
   align) or unnecessary complexity (deferred recording for
   `equation` where it's not needed).

2. **Why ranges for multi-line environments?**  Per-line equation
   numbers in `align` require either patching `\refstepcounter`
   (fragile — cleveref adds optional args) or deferring to
   `\label` time (correct only when `\label` is present, noisy
   warnings otherwise).  Ranges are always correct, always
   available (computed from counter at env boundaries), and
   semantically appropriate (an `align` block is one derivation).

3. **Why parenthesized display numbers as keys?**  Parentheses
   `(` `)` are catcode 12 in TeX and valid in `\csname` keys.
   Using `(4.1)` instead of `eq:4.1` as the internal key means
   the rendering code (`\codep@brhyper`, `\codep@collapsebr`)
   requires minimal changes.

4. **Why not patch `\refstepcounter`?**  cleveref adds an optional
   argument; hyperref also patches it.  A chain of patches is
   fragile across package versions.

5. **Why `\ifmeasuring@` instead of choosing which patches to
   install?**  Even if we skip the `\@setref` patch when cleveref
   is loaded, the measuring pass still fires `\ref` twice.
   `\ifmeasuring@` is a single guard that handles both problems
   (double-patch + measuring pass) at the entry point.

6. **Why inject `\hypertarget` at `\begin{align}`?**  At
   `\end{align}`, `\@currentHref` points to the last row's
   hyperref anchor, not the block.  If all rows have `\notag`,
   `\@currentHref` is stale from whatever preceded the align.
   A dedicated anchor is reliable.

7. **Why not counter-share?**  The old `equations=shared` mode
   was removed — see REVIEW_E #6.

#### Edge cases (from adversarial review)

- **All-`\notag` align:** counter doesn't advance → no range
  to compute.  Fall through to containing atom or silently drop.
- **`\subequations` wrapping align:** `\theequation` is redefined
  to `\theparentequation\alph{equation}`, which is in scope
  during the `\begingroup` computation.  Range `(1a--1c)` is
  correct.
- **Consecutive align blocks:** pending list must be cleared at
  `\begin{align}`.  Assert empty or clear unconditionally.
- **`paragraphs=off` + `equations=outer`:** deferred flush at
  `\end{align}` must perform the same mode/theorem guard as
  `\codep@writeatomref`.
- **`gather`/`flalign`:** same Track 2 behaviour as `align`;
  different amsmath internals but same `\AtBeginEnvironment` /
  `\AtEndEnvironment` hooks work uniformly.

#### Fragility assessment

| Component | Rating | Depends on |
|-----------|--------|------------|
| `\AtBeginEnvironment` / `\AtEndEnvironment` | **Robust** | Documented etoolbox/LaTeX interfaces |
| `\c@equation` read at env boundaries | **Robust** | Standard counter access |
| `\theequation` in `\begingroup` for formatting | **Robust** | Standard TeX grouping |
| `\ifmeasuring@` guard | **Robust** | Documented amsmath conditional |
| `\hypertarget` anchor injection | **Robust** | Documented hyperref interface |
| Parentheses and `--` in csname keys | **Robust** | Catcode 12, all engines |
| Assumption: counter monotonically increases in align | **Moderate** | Standard amsmath behaviour; `\notag` doesn't decrement |

#### Number-first theorem headers

Some authors prefer "1.1 Theorem" instead of "Theorem 1.1"
(Bourbaki, EGA, Stacks Project style).  This is a theorem
formatting concern, not a dependency tracking concern.
codependent does not override theorem headers.

To achieve this with amsthm:

```latex
\newtheoremstyle{numberfirst}%
  {}{}%                          % space above/below
  {\itshape}%                    % body font
  {}%                            % indent
  {\bfseries}%                   % head font
  {.}%                           % punctuation after head
  { }%                           % space after head
  {\thmnumber{#2} \thmname{#1}\thmnote{ (#3)}}%  number first
\theoremstyle{numberfirst}
```

### Paragraph numbering

Every paragraph gets a number via `\AddToHook{para/begin}`.
Rendered as a small superscript in the left margin:

```
^{1.1}  A category C consists of the following data...

^{1.2}  subject to the following axioms...
```

Small, unobtrusive, does not interrupt text flow.

#### Suppression mechanism

A depth counter `\codep@nestlevel` controls suppression.
When `\codep@nestlevel > 0`, the `para/begin` hook skips
numbering.  Any environment or command that should suppress
numbering increments `\codep@nestlevel` on entry and decrements
on exit.

**Suppressed environments** (via `\AtBeginEnvironment` /
`\AtEndEnvironment`):
- List environments: `enumerate`, `itemize`, `description`
- Quoting: `quote`, `quotation`
- Floats: `figure`, `table`
- Boxes: `minipage`
- Tables: `tabular`, `tabularx`, `longtable`
- Theorem environments (see below — they get one number
  for the whole environment, not per-paragraph)

**Suppressed commands** (via `etoolbox` `\pretocmd` /
`\apptocmd` patching):
- `\footnote` — increment `\codep@nestlevel` before body,
  decrement after
- `\parbox` — same
- `\caption` — same

**User-extensible:**
```latex
\codepsuppress{myenvironment}   % for environments
\codepsuppresscmd{\mycommand}   % for commands
```

**Sectioning commands** (`\section`, `\subsection`, etc.)
suppress the heading paragraph itself.  The first content
paragraph after a section heading IS numbered.

### Theorem environment numbering

Hooked via `etoolbox`'s `\AtBeginEnvironment` and
`\AtEndEnvironment` for each environment name registered
with `\codeptrack{...}`.  No dependency on `thmtools` —
works with plain `amsthm`, `ntheorem`, or raw `\newtheorem`.

When a tracked environment opens:

1. Set `\codep@nestlevel > 0` so paragraphs within the
   environment don't get separate numbers.
2. Adjust the displayed number to use the atom format.

The `\AtBeginEnvironment{<env>}` hook (etoolbox) fires
BEFORE the env's begin command runs, which means BEFORE
amsthm's `\@thm` calls `\refstepcounter{theorem}`.  At
hook entry, `\theatom` therefore expands to the
**previous** atom's display number, not the current one.
Source: etoolbox.sty:1803-1824 (`\csgappto{@begin@foo@hook}`
prepended to `\begin`'s expansion); amsthm.sty:129-149
(`\refstepcounter{#2}` at line 145 of `\@thm`).

Consequence: the hook body cannot reliably *cache* the
current atom number.  Instead, every site that needs the
current atom number reads `\theatom` directly at use time
(e.g. `\codep@writeatomref` reads `\theatom` when emitting
the source field of a `\codep@atomref` record, not the
cached `\codep@currentatom`).  The cached
`\codep@currentatom` is repurposed as an **in-atom
sentinel**: empty = no current atom; non-empty = inside a
tracked atom (specific value irrelevant).

The hook still runs (it sets the in-atom sentinel,
increments `\codep@nestlevel`, queues backref display, and
clears the sentinel at atom end).  What it does NOT do is
freeze the atom number into a macro.

When it closes, decrement `\codep@nestlevel`.

Result: "Definition 2.3." uses the same counter as
paragraph 2.2 before it.  Multiple paragraphs within a
single definition share one number.

**Nested tracked environments:** if `\codep@nestlevel > 0`
when a tracked environment opens (i.e., it's inside another
tracked environment), the counter is NOT advanced.  The inner
environment is part of the outer atom.  Example: a
`definition` containing an `example` gets one atom number.

**Starred environments:** `\codeptrack{definition}` auto-
registers both `definition` and `definition*`.  Both get atom
numbers.

### Proof environments

`proof` (from `amsthm`) is not a `\newtheorem` environment.
It is hooked separately via `\AtBeginEnvironment{proof}`.

By default, proofs get their own atom number (Pavlov style).
The number renders as a superscript margin number (like
paragraphs); the "Proof." heading from `amsthm` stays as-is.

```latex
\usepackage[proofs=numbered]{codependent}    % default
\usepackage[proofs=unnumbered]{codependent}  % skip numbering
```

### Labels

No auto-generated labels.  Authors use explicit `\label{...}`
as usual.  The `.sty` does not create labels because
display-number-based labels would be unstable under
reorganization.

## Aux file protocol

The `.sty` writes structured data to the `.aux` file so that
the codependent CLI can compute back-references.  This follows the
standard LaTeX pattern used by `hyperref`, `cleveref`, etc.

### Atom registration

When each atom is created (in the `para/begin` hook or at
theorem environment entry), the `.sty` writes:

```tex
\codep@atom{1.2.3}{paragraph}
\codep@atom{1.2.4}{Definition}
```

Format: `\codep@atom{display-number}{type}`.  The type is
the display name for theorem environments (e.g., "Definition",
"Theorem") or "paragraph" for plain paragraphs.  This is a
display name, not a programmatic identifier.

No label is included — the CLI associates labels to atoms by
matching `\newlabel{...}{{1.2.4}{...}}` entries to atom
numbers.

### Reference tracking

The `.sty` patches `\@setref` — the internal kernel command
that ALL reference commands (`\ref`, `\eqref`, `\autoref`,
`\cref`) eventually call.  One patch point, works regardless
of what redefines the user-facing commands (hyperref, cleveref,
etc.).

When `\@setref` fires inside a tracked atom, the `.sty`
writes:

```tex
\codep@atomref{1.2.5}{def:category}
\codep@atomref{1.2.5}{eq:composition}
```

Format: `\codep@atomref{current-atom-number}{target-label}`.
Only written when `\codep@currentatom` is non-empty (i.e.,
inside a tracked atom context).

### Safety

On pass 1 (no prior `.aux` exists), both `\codep@atom` and
`\codep@atomref` are defined as `\providecommand` no-ops in
the preamble so that LaTeX's aux read (which happens at
`\begin{document}`) does not error when no records are
present.

On pass 2 (and all subsequent reruns), the preamble installs
active definitions **before** the aux read (pin point:
`\AtEndPreamble` / `begindocument/before`, see Section 8a
"Load order" for the exact hook).  The active definitions
turn `\codep@atomref{src}{tgt}` into an enqueue onto the
back-ref defer queue — exactly Pavlov's `\recordbackref`
pattern, adapted to LaTeX's `.aux` rerun as the inter-pass
persistence layer.

### Staleness detection

Dropped.  The superseded design used a content hash to
detect `.sbr` / `.aux` drift; with the `.sbr` file gone,
LaTeX's own rerun mechanism (`rerunfilecheck`, latexmk,
kernel `Label(s) may have changed` warnings) already handles
drift detection.  The `.sty` emits a `\PackageInfo` when a
pass 2 flush produces a different `\codep@br@*` population
than the preamble expected.

## Back-references

**The back-reference pipeline is defined in Section 8a below.**
It is entirely in-TeX (ported from dpmac), runs during the
normal pdflatex rerun cycle, and does not use any external
tool or `.sbr` sidecar.  The previous three-file design
(`.aux -> codependent-cli -> .sbr`) is archived under
`tools/codependent-cli/reviews/` as the pre-port architecture.

### Display modes (unchanged)

At the point where a populated back-ref list is available
(Section 8a), it is rendered in one of three modes:

**Inline mode (default).**  At the end of each atom, if
back-ref data exists, the `.sty` appends

```
                            Used in 2.1, 3.4, 5.2.
```

rendered in `\small\sffamily`.  Each number is a hyperlink
when `hyperref` is loaded.  The rendering is performed by
`\codep@renderinline` (currently present in `codependent.sty`
Section 8).  The only change required by the port is the
*source* of the pending list: instead of being populated
from `.sbr`-file data, it is populated from the csname
`\codep@br@<num>` that Section 8a's graph inversion
produced during the `begindocument` flush.

**Appendix mode.**  Back-refs are collected during the same
csname walk and typeset via `\codepappendix`.  Grouping
by section title is derived from the TOC entries LaTeX
already writes to `.aux`.

```
Dependency Index

1  Categories
   1.2  Category .............. 2.1, 2.3, 3.1, 3.4, 4.2,
                                5.1, 5.3, 7.2
   1.3  Hom-set ............... 2.1, 4.1
```

**None mode.**  Numbering only, no back-references
displayed.  The Section-8a graph inversion is still run
(cheap) but the rendering step is skipped.

## Section 8a — Back-reference graph (ported from dpmac, GPLv3)

> Portions of this section are derived from `dpmac.tex` by
> **Dmitri Pavlov** (Copyright 2017, 2018 Dmitri Pavlov,
> distributed under GNU GPL version 3).  The derivative in
> `codependent.sty` is Copyright 2026 and is also distributed under
> GNU GPL version 3.  Original source:
> <https://dmitripavlov.org/tex/dpmac.tex>.  See
> `tools/codependent/CREDITS.md` for the provenance table.

### Intent

A back-reference link from "Proposition 2.1" down to
"Definition 1.2" is written by the author as
`\ref{def:cat}` inside Proposition 2.1.  To display the
*reverse* arrow ("Definition 1.2 is used in 2.1") the `.sty`
must invert the reference graph.  Pavlov's `dpmac.tex`
solves this in ~45 lines of Plain TeX using two token
registers and a family of per-target csnames.  Section 8a
adapts that algorithm to LaTeX2e, with LaTeX's own `.aux`
rerun acting as the inter-pass persistence layer that
Pavlov implements with an explicit two-pass driver.

### Walkthrough (two-pass protocol)

Two pdflatex runs are involved, identical to the normal
LaTeX rerun cycle:

1. **Pass 1 (collection).**  On each `\ref` (via the
   `\@setref` patch installed by Section 8a.0 below), the
   `.sty` writes `\codep@atomref{src}{tgt}` to `.aux`,
   where `src` is the current atom display number and `tgt`
   is the label key.  If no current atom is active
   (`\codep@currentatom` is empty), nothing is written —
   see Section 8a.5 "currentatom state management" below.

2. **Pass 2 (inversion).**  Before LaTeX reads `.aux`
   inside `\begin{document}`, the preamble installs active
   definitions for `\codep@atomref` and for a `\newlabel`
   override (pinned at `\AtEndPreamble` per REVIEW_C
   finding #3; see "Load order" below).  As `.aux` is read,
   each `\newlabel` entry populates
   `\codep@lblnum@<key>` with the label's display number,
   and each `\codep@atomref` call enqueues a
   `\codep@processbr` invocation onto the defer queue.
   After `.aux` is fully read, a single flush iterates the
   queue, populating per-target node csnames
   `\codep@brnode@<num>@<k>` with the inverted lists.
   Typesetting then proceeds; at each atom's
   `\codep@queuebackref` call site, `\codep@collapsebr`
   lazily materialises `\codep@br@<num>` from the per-
   target nodes (see Section 8a.6 for the edit to
   `\codep@queuebackref` that triggers this collapse); the
   `\codep@flushbackref` hook then reads that csname and
   the existing `\codep@renderinline` prints "Used in X, Y."

The persistence layer is LaTeX's `.aux`; no `.sbr` file is
involved.  Graph inversion runs once per pdflatex pass, in
TeX, in bounded time (see "Performance" below).

### Pipeline summary (per D#3)

End-to-end data flow, with hook names and macro names
pinned so an implementer can trace each step back to a
specific section of the sketch:

```
Pass 1 (collection):
  para/begin (codependent.sty Section 7)
    -> \refstepcounter{atom}
    -> \edef\codep@currentatom{\theatom}
    -> \codep@queuebackref{\codep@currentatom}
         [on pass 1 this is a no-op; the csnames do not
          exist yet.  Edit lives in Section 8a.6.]
  \ref / \eqref / \autoref / \cref  (any reference command)
    -> \@setref (patched in Section 8a.0)
    -> if \codep@currentatom non-empty:
         \immediate\write \@auxout
           \codep@atomref{\codep@currentatom}{<label>}
  para/end  (codependent.sty Section 7)
    -> \codep@flushbackref         [no-op on pass 1]
    -> \let\codep@currentatom\@empty   (Section 8a.5)
Between passes:
  LaTeX rewrites main.aux with the current set of
  \codep@atomref records (interleaved with standard
  \newlabel records).
Pass 2 (inversion + render):
  \AtEndPreamble / begindocument/before
    -> \codep@installatomrefpatch   (Section 8a.0)
    -> \codep@installnewlabel       (Section 8a.4)
  \begin{document} -> kernel \@input{\jobname.aux}
    -> each \newlabel record:
         \codep@extractlblnum updates \codep@lblnum@<key>
    -> each \codep@atomref{src}{tgt} record:
         \codep@recordbr           (Section 8a.1)
         -> \xdef \csname codep@brq@N \endcsname
              {\codep@processbr{tgt}{src}}
  begindocument/end
    -> \codep@flushbrqueue         (Section 8a.1)
    -> walks brq@1..brq@brid, firing \codep@processbr
    -> \codep@processbr            (Section 8a.3)
    -> populates \codep@brcount@<tgt>
       and \codep@brnode@<tgt>@<k>
  para/begin for atom N, or AtBeginEnvironment for tracked env
    -> \codep@queuebackref{N}      (Section 8a.6 EDIT)
    -> \codep@collapsebr{N} (lazy; first call only)
       -> joins brnode@N@1 .. brnode@N@count with ", "
       -> \xdef \csname codep@br@N \endcsname{<joined>}
    -> reads \csname codep@br@N \endcsname into
       \codep@pendingbr
  para/end (or \AtEndEnvironment)
    -> \codep@flushbackref -> \codep@renderinline
       -> typesets "Used in X, Y."
    -> \let\codep@currentatom\@empty
```

The pipeline has TWO halves that must both be in place:
the aux-WRITE patch (Section 8a.0) AND the aux-READ
callbacks (Sections 8a.1-8a.4).  Implementers must not
skip either half.

### Reference implementation sketch

The following TeX code is the blueprint for the Section 8a
insertion into `codependent.sty`.  It incorporates the fixes
from REVIEW_C (findings #1, #2, #3, #4) and is written to
be valid-shape — every brace and `\fi` balances, every
`\csname` closes, every `\expandafter` has a target.
2-space indent.

### Section 8a.0 overview — Reference interception (REVIEW_D #3, REVIEW_E #1)

> Upstream motivation: REVIEW_D finding #3 mandated that
> an aux-WRITE patch exist at all (previous revision
> referenced one without defining it).  **REVIEW_E finding
> #2 then proved that the single-`\@setref` patch that
> REVIEW_D asked for covers only a fraction of real
> reference traffic: `\cref`/`\Cref`/`\labelcref` bypass
> `\@setref` via cleveref's `\cref@getlabel`,
> `\autoref` bypasses via hyperref's
> `\HyRef@autosetref`, and `\ref*`/`\Ref` bypass via
> `\HyRef@@StarSetRef`→`\real@setref` (the hyperref
> saved copy of `\@setref`, which predates our wrap).**
> A math monograph using cleveref has ~0% back-reference
> graph coverage from the REVIEW_D single-patch design.

The corrected design installs **three patch sites**, not
one:

1. Kernel `\@setref` — covers `\ref`, `\eqref`,
   `\pageref` (via `\@pagesetref` delegation), `\vref`
   (varioref uses `\ref` internally), and `\nameref`
   (nameref.sty line 326 calls `\@setref` directly).
2. cleveref `\cref@getlabel` — covers every cleveref
   family command (`\cref`, `\Cref`, `\labelcref`,
   `\cpageref`, `\Cpageref`, `\crefrange`, `\Crefrange`,
   `\namecref`, `\nameCref`).
3. hyperref `\HyRef@autosetref` (for `\autoref`) and
   `\HyRef@@StarSetRef` (for `\ref*`/`\Ref`).

The section opening prose said "ALL reference commands
eventually call `\@setref`" in previous revisions.  That
claim is **false**; each reference package built its own
dispatcher to support package-specific output formatting
(custom labels for `\cref`, name-lookup for `\autoref`,
no-hyperlink fallback for `\ref*`) and there is no
canonical entry point.

#### Coverage table (verbatim from REVIEW_E finding #2)

| Command | Covered by `\@setref` patch alone? | Covered by 3-site design? |
|---|---|---|
| `\ref{foo}` | yes | yes |
| `\eqref{foo}` | yes (goes through `\ref`) | yes |
| `\pageref{foo}` | partial (via `\@pagesetref`) | partial (good enough; pageref is rarely an atom-reference) |
| `\vref{foo}`, `\Vref{foo}`, `\vpageref{foo}` | yes (varioref uses `\ref`) | yes |
| `\nameref{foo}` | yes (nameref.sty line 326) | yes |
| `\autoref{foo}` | **NO** | yes (via `\HyRef@autosetref`) |
| `\ref*{foo}` | **NO** | yes (via `\HyRef@@StarSetRef`) |
| `\Ref{foo}` (hyperref) | **NO** | yes (via `\HyRef@@StarSetRef`) |
| `\hyperref[foo]{text}` | **NO** | **NO** (deliberately uncovered; see below) |
| `\cref{foo}`, `\Cref{foo}` | **NO** | yes (via `\cref@getlabel`) |
| `\crefrange{a}{b}`, `\Crefrange{a}{b}` | **NO** | yes |
| `\labelcref{foo}` | **NO** | yes |
| `\cpageref{foo}`, `\Cpageref{foo}` | **NO** | yes |
| `\namecref{foo}`, `\nameCref{foo}` | **NO** | yes |

Deliberately uncovered: `\hyperref[label]{text}` — see
the "Deliberately uncovered" subsection below.

#### Why so many patch sites?

The back-reference graph has to record every edge from an
atom to a labelled target.  Each reference package in
common use dispatches through its own internal macro:

- **Kernel `\@setref` (latex.ltx).**  The original and
  simplest: every `\ref`/`\pageref` invocation calls
  `\@setref{\r@<label>}{<selector>}{<label>}` and we
  intercept at that point.
- **cleveref `\cref@getlabel` (cleveref.sty lines
  1044-1178).**  cleveref reads
  `\csname r@<label>@cref\endcsname` directly — the
  `@cref`-suffixed record that cleveref writes to
  `.aux` alongside the kernel `\newlabel`.  It calls
  `\cref@getlabel{<label>}{<temp-macro>}` which loads
  the cref-style fields into `<temp-macro>`.  Every
  cleveref family command routes through this helper,
  so patching it once covers the whole family.
- **hyperref `\HyRef@autosetref` (hyperref.sty line
  8220-8244).**  `\autoref` reads the cref-style
  fields from `\csname r@<label>\endcsname` to produce
  "Theorem 2.5" (with the type-name prefix looked up
  from `\autoref@name@theorem`).  It never calls
  `\@setref`.
- **hyperref `\HyRef@@StarSetRef` (hyperref.sty lines
  8133-8137).**  `\ref*`/`\Ref` produce the reference
  text without a hyperlink, by calling
  `\real@setref` — the copy of `\@setref` that hyperref
  saved at load time, before any wrapping.  Because
  our `\@setref` patch sees hyperref's wrapped
  `\@setref` (not `\real@setref`), `\ref*` bypasses us
  via the saved copy.  Patching `\HyRef@@StarSetRef`
  catches both `\ref*` and `\Ref`.

**Load-bearing consequence: `\cref@getlabel` is called
MULTIPLE TIMES per `\cref` invocation** — once for each
label in a cref list like `\cref{thm:A,thm:B,thm:C}`.
Every call produces a `\codep@atomref` write.  The
downstream deduplication in `\codep@processbr`
(Section 8a.3) must absorb this multiplicity; the
per-target `\codep@brlast@<tgt>` consecutive-dedup
handles the common case (same source atom to same target
target on the same line) automatically.  For the
multi-label-list case, deduplication happens on pass 2
at processing time, so the `.aux` file may contain K
duplicate records for a K-label `\cref` — harmless but
visible to anyone who greps `.aux`.

#### Deliberately uncovered: `\hyperref[label]{text}`

Per REVIEW_E finding #16 (NITPICK): `\hyperref[foo]{text}`
is an author-hand-rolled hyperlink, not a
cross-reference.  The author is explicitly saying "I
want a link here, not a semantic reference."  codependent
does **not** record it as a back-reference edge.  Users
who want back-ref tracking should write `\cref{label}`
(or `\ref{label}`) instead.

If a user genuinely wants both the hand-rolled display
text AND back-ref tracking, they can write
`\cref{label}` inline with a `\footnote{see ...}` — or
explicitly call `\codep@recordmanualref{label}` (a
helper we may provide in a later revision; not
promised).

#### Implementation sketch

```tex
%% ------------------------------------------------------------
%% Section 8a.0: Reference interception (three-site design).
%% Per REVIEW_E finding #2 (BLOCKER), the previous
%% single-\@setref patch is insufficient: cleveref, hyperref
%% \autoref, and hyperref \ref*/\\Ref all bypass \@setref.
%% This subsection installs THREE patches instead of one.
%% Per REVIEW_E finding #16, \hyperref[]{} is deliberately
%% uncovered (manual link, not a cross-reference).
%% Per REVIEW_E finding #3, \ref* coverage is subsumed by
%% the \HyRef@@StarSetRef patch below.
%% ------------------------------------------------------------

% Pass-1 safety: \codep@atomref must be defined to SOMETHING
% at package-load time so that if a stale pass-0 .aux still
% references it (or a user-script injects a record), LaTeX's
% aux read does not error.  A \providecommand no-op suits.
\providecommand*{\codep@atomref}[2]{}

% Shared aux-write helper called by all patch sites.
% Guards on \codep@currentatom per Section 8a.5, and on
% \if@filesw so --draftmode / -no-aux compiles work.
\def\codep@writeatomref#1{%
  \ifx\codep@currentatom\@empty\else
    \if@filesw
      \protected@write\@auxout{}{%
        \string\codep@atomref
          {\codep@currentatom}{#1}%
      }%
    \fi
  \fi
}

% \codep@installatomrefpatch
%   Install all three patch sites.  Called from the
%   begindocument/before hook (Section 8a.7), AFTER
%   hyperref/cleveref have finished wrapping their
%   respective dispatchers.  Patching at this point means
%   we wrap the OUTERMOST live definition, preserving
%   every prior hook (hyperlink emission, cref formatting).
\def\codep@installatomrefpatch{%
  %% ---- Patch 1: kernel \@setref ----
  %% Covers \ref, \eqref, \pageref (via \@pagesetref
  %% delegation), \vref, \Vref, \vpageref, \nameref.
  \let\codep@orig@setref\@setref
  \def\@setref##1##2##3{%
    \codep@orig@setref{##1}{##2}{##3}%
    \codep@writeatomref{##3}%
  }%
  %% ---- Patch 2: cleveref \cref@getlabel ----
  %% Covers every cleveref family command.
  \@ifpackageloaded{cleveref}{%
    \let\codep@orig@crefgetlabel\cref@getlabel
    \def\cref@getlabel##1##2{%
      \codep@orig@crefgetlabel{##1}{##2}%
      \codep@writeatomref{##1}%
    }%
  }{}%
  %% ---- Patch 3: hyperref \HyRef@autosetref / \HyRef@@StarSetRef ----
  %% \HyRef@autosetref covers \autoref.
  %% \HyRef@@StarSetRef covers \ref* and \Ref.
  %% Subsumes REVIEW_E finding #3 (\ref* bypass).
  \@ifpackageloaded{hyperref}{%
    \@ifundefined{HyRef@autosetref}{}{%
      \let\codep@orig@HyRefautosetref\HyRef@autosetref
      \def\HyRef@autosetref##1##2##3{%
        \codep@orig@HyRefautosetref{##1}{##2}{##3}%
        \codep@writeatomref{##2}%
      }%
    }%
    \@ifundefined{HyRef@@StarSetRef}{}{%
      \let\codep@orig@HyRefStarSetRef\HyRef@@StarSetRef
      \def\HyRef@@StarSetRef##1##2##3{%
        \codep@orig@HyRefStarSetRef{##1}{##2}{##3}%
        \codep@writeatomref{##2}%
      }%
    }%
  }{}%
}

%% ------------------------------------------------------------
%% Section 8a.1: defer queue via csname linked list.
%% Per REVIEW_C finding #2, the toks-register pattern from
%% dpmac is O(N^2) at 15k refs; replaced with a csname
%% linked list keyed by a monotonic \codep@brid counter.
%% ------------------------------------------------------------
\newcount\codep@brid
\codep@brid=0\relax

% \codep@recordbr{src}{tgt}
%   Enqueue a processbackref call.  O(1) per append.
\def\codep@recordbr#1#2{%
  \global\advance\codep@brid by 1\relax
  \expandafter\xdef\csname codep@brq@\the\codep@brid\endcsname
    {\noexpand\codep@processbr{#2}{#1}}%
}

% \codep@flushbrqueue
%   Walk the linked list once, O(N) total.  Called from the
%   begindocument hook with explicit ordering (see "Queue
%   flush timing" below).
\def\codep@flushbrqueue{%
  \begingroup
    \count@=\z@
    \loop
      \ifnum\count@<\codep@brid
        \advance\count@ by 1\relax
        \csname codep@brq@\the\count@\endcsname
        \global\expandafter\let
          \csname codep@brq@\the\count@\endcsname\relax
    \repeat
  \endgroup
}

%% ------------------------------------------------------------
%% Section 8a.2: .aux record callback.
%% The providecommand no-op from Section 8a.0 is REPLACED by
%% this active definition at begindocument/before (Section
%% 8a.7), before LaTeX reads .aux in \begin{document}.  From
%% that point on, every \codep@atomref{src}{tgt} that the
%% .aux read fires lands here and enqueues a processbackref
%% call.
%%
%% Per REVIEW_C finding #4, guard on empty src (orphan refs
%% emitted between atoms).  The guard is belt-and-braces: the
%% \@setref patch in Section 8a.0 already skips the write
%% when \codep@currentatom is empty, so a well-formed .aux
%% should never deliver an empty-src record here; we guard
%% anyway in case a user hand-edits the aux or a legacy file
%% sneaks in.
%% ------------------------------------------------------------
\def\codep@atomref@active#1#2{%
  \edef\codep@tmp@src{#1}%
  \ifx\codep@tmp@src\@empty\else
    \codep@recordbr{#1}{#2}%
  \fi
}

%% ------------------------------------------------------------
%% Section 8a.3: per-target linked list (O(degree), not
%% O(degree^2)).  Per REVIEW_C finding #2 second half.
%%
%% For each target atom we maintain:
%%   \codep@brcount@<num>  -- count of appended refs
%%   \codep@brnode@<num>@<k> -- the k-th ref text
%% At typeset time the nodes are collapsed into the
%% display macro \codep@br@<num>.
%% ------------------------------------------------------------
\def\codep@processbr#1#2{%
  % #1 = target label key
  % #2 = source atom display number
  \expandafter\ifx\csname codep@lblnum@#1\endcsname\relax
    % Unknown target: silently drop.  This is the same
    % behaviour as dpmac's \ewarningline, minus the warning.
  \else
    \edef\codep@tmp@tgt{\csname codep@lblnum@#1\endcsname}%
    \edef\codep@tmp@src{#2}%
    % Self-ref guard (REVIEW_C finding #10).  Both sides are
    % \edef'd so comparison is on display-number strings.
    \ifx\codep@tmp@src\codep@tmp@tgt\else
      % Dedup against previous append for this target.
      % (Per REVIEW_D finding #1, an earlier draft had a
      % dead \ifx placeholder here; removed.)
      \edef\codep@tmp@last{%
        \csname codep@brlast@\codep@tmp@tgt\endcsname}%
      \ifx\codep@tmp@last\codep@tmp@src
        % Consecutive duplicate: skip.
      \else
        \global\expandafter\let
          \csname codep@brlast@\codep@tmp@tgt\endcsname
          \codep@tmp@src
        % Append a new linked-list node.
        \expandafter\ifx
            \csname codep@brcount@\codep@tmp@tgt\endcsname\relax
          \global\expandafter\def
            \csname codep@brcount@\codep@tmp@tgt\endcsname{0}%
        \fi
        \edef\codep@tmp@k{%
          \csname codep@brcount@\codep@tmp@tgt\endcsname}%
        \count@=\codep@tmp@k\relax
        \advance\count@ by 1\relax
        \expandafter\xdef
          \csname codep@brcount@\codep@tmp@tgt\endcsname
          {\the\count@}%
        \expandafter\xdef
          \csname codep@brnode@\codep@tmp@tgt @\the\count@\endcsname
          {#2}%
      \fi
    \fi
  \fi
}

% \codep@collapsebr{targetnum}
%   Build a comma-joined display macro \codep@br@<num>
%   from the per-target node csnames.  Called lazily the
%   first time \codep@queuebackref looks up <num>.
\def\codep@collapsebr#1{%
  \expandafter\ifx\csname codep@brcount@#1\endcsname\relax
    % No refs to this target.
    \global\expandafter\let\csname codep@br@#1\endcsname\@empty
  \else
    \begingroup
      \edef\codep@tmp@n{\csname codep@brcount@#1\endcsname}%
      \def\codep@tmp@acc{}%
      \count@=\z@
      \loop
        \ifnum\count@<\codep@tmp@n
          \advance\count@ by 1\relax
          \edef\codep@tmp@node{%
            \csname codep@brnode@#1@\the\count@\endcsname}%
          \ifx\codep@tmp@acc\@empty
            \edef\codep@tmp@acc{\codep@tmp@node}%
          \else
            \edef\codep@tmp@acc{%
              \codep@tmp@acc, \codep@tmp@node}%
          \fi
      \repeat
      \global\expandafter\let
        \csname codep@br@#1\endcsname\codep@tmp@acc
    \endgroup
  \fi
}

%% ------------------------------------------------------------
%% Section 8a.4: \newlabel override.
%% Per REVIEW_C finding #1, use \@secondoftwo-style grab of
%% the first braced subgroup.  Per REVIEW_C finding #3, pin
%% installation at \AtEndPreamble so hyperref's pre-2023
%% aux-injection block does not clobber it.  Also patch
%% \newlabelxx to cover the pre-2023 hyperref pathway.
%% ------------------------------------------------------------
\def\codep@grabfirst#1#2\@nil{#1}
\def\codep@installnewlabel{%
  \let\codep@orig@newlabel\newlabel
  \def\newlabel##1##2{%
    \codep@orig@newlabel{##1}{##2}%
    \codep@extractlblnum{##1}{##2}%
  }%
  % Pre-2023 hyperref path: \newlabelxx#1#2#3#4#5#6 -> \oldnewlabel
  % We override \newlabelxx too, since hyperref installs it in
  % \AtBeginDocument and it races with our override.
  \@ifundefined{newlabelxx}{}{%
    \let\codep@orig@newlabelxx\newlabelxx
    \def\newlabelxx##1##2##3##4##5##6{%
      \codep@orig@newlabelxx{##1}{##2}{##3}{##4}{##5}{##6}%
      % ##2 is already the display number for the 6-arg form.
      \expandafter\gdef
        \csname codep@lblnum@##1\endcsname{##2}%
    }%
  }%
}

% \codep@extractlblnum{key}{value}
%   value is the raw 2nd arg of \newlabel, which after TeX
%   brace-stripping is already "{num}{page}{...}{...}{...}".
%   We grab the first brace group and stash it under the key.
%   Skip keys that end in @cref (cleveref internal records).
\def\codep@extractlblnum#1#2{%
  \codep@ifcrefkey{#1}{%
    % @cref-suffixed: skip silently.
  }{%
    % Extract first subgroup via \codep@grabfirst.
    \expandafter\codep@extractlblnum@ii
      \expandafter{\codep@grabfirst#2\@nil}{#1}%
  }%
}
\def\codep@extractlblnum@ii#1#2{%
  \expandafter\gdef\csname codep@lblnum@#2\endcsname{#1}%
}

% \codep@ifcrefkey{key}{then}{else}
%   True iff the label key ENDS in "@cref" (not merely
%   contains it).  Per REVIEW_D finding #4, an earlier draft
%   matched any key containing "@cref", which incorrectly
%   dropped keys like "lemma@crefnum" that happen to contain
%   "@cref" as a prefix of a longer suffix.  Fixed below.
%
% Algorithm: the delimited-arg probe splits "<key>@cref\@nil"
% on the FIRST occurrence of "@cref".  ##2 is the tail of
% the split (everything after @cref, up to \@nil).
% Outcomes:
%   key = foo              -> probe "foo@cref\@nil"
%                          -> ##1=foo, ##2=(empty) -> NOT cref
%   key = foo@cref         -> probe "foo@cref@cref\@nil"
%                          -> ##1=foo, ##2=@cref -> IS cref
%   key = foo@crefnum      -> probe "foo@crefnum@cref\@nil"
%                          -> ##1=foo, ##2=num@cref -> NOT cref
%   key = foo@cref@bar     -> probe "foo@cref@bar@cref\@nil"
%                          -> ##1=foo, ##2=@bar@cref -> NOT cref
%
% The rule "IS cref iff ##2 == '@cref'" detects the
% sentinel-only tail, which happens exactly when the
% ORIGINAL key ended in "@cref" and the probe's own trailing
% "@cref" is what matched.
\def\codep@ifcrefsentinel{@cref}
\def\codep@ifcrefkey#1{%
  % Side-effect style: set a boolean, then dispatch on it.
  % Clearer than nested-\expandafter skip-out-of-two-\fis,
  % and avoids the three-\expandafter trick that REVIEW_D
  % finding #4 cautions against.
  \codep@iscreffalse
  \def\codep@ifcrefkey@probe##1@cref##2\@nil{%
    \def\codep@tmp@b{##2}%
    \ifx\codep@tmp@b\@empty
      % No @cref in the key at all -> the probe's own
      % trailing @cref absorbed the split -> NOT a cref key.
    \else
      % @cref found somewhere.  IS-cref iff the tail is
      % EXACTLY "@cref" (meaning the probe's own trailing
      % @cref is what matched, i.e. the key ended in @cref).
      \ifx\codep@tmp@b\codep@ifcrefsentinel
        \codep@iscreftrue
      \fi
    \fi
  }%
  \codep@ifcrefkey@probe#1@cref\@nil
  \ifcodep@iscref
    \expandafter\@firstoftwo
  \else
    \expandafter\@secondoftwo
  \fi
}
% Flag declared once; used only inside \codep@ifcrefkey.
\newif\ifcodep@iscref

%% ------------------------------------------------------------
%% Section 8a.7: hook installation.
%% Per REVIEW_D finding #2, the two codependent-owned labels on
%% begindocument/before get EXPLICIT relative ordering rather
%% than both claiming "before *".  Two "before *" rules in
%% the same package pile up and give no guarantee about their
%% relative order if a future edit introduces a dependency.
%% ------------------------------------------------------------

% Install the \@setref aux-write patch AND the \newlabel
% override + the active \codep@atomref callback at
% begindocument/before.  All three belong together in one
% hook because they co-depend on being in place before the
% .aux read during \begin{document}.
\AddToHook{begindocument/before}[codependent/backref/install]{%
  \codep@installatomrefpatch
  \codep@installnewlabel
  % Swap the providecommand no-op for the active callback.
  \let\codep@atomref\codep@atomref@active
}

% Flush the queue AFTER aux has been read.  The aux read
% happens during the kernel's \document macro before any
% \AtBeginDocument hook fires, so begindocument/end is a
% safe point.  No internal ordering constraint vs. codependent's
% own labels on this hook (there is only one).
\AddToHook{begindocument/end}[codependent/backref/flush]{%
  \codep@flushbrqueue
}
```

**Hook-rule declarations** (per REVIEW_D #2).  The two
codependent labels on `begindocument/before`
(`codependent/backref/install` from Section 8a.7 and
`codependent/sbl/open` from Section 9a) are given an explicit
internal order: the backref install must run before the
sbl open, because the sbl writer depends on the
`\codep@currentatom` / `\@setref` patch infrastructure
being live.  No label claims `before *` any longer.

```tex
% Internal dependency: sbl open sees the backref install.
\DeclareHookRule{begindocument/before}{codependent/sbl/open}%
                {after}{codependent/backref/install}

% Note (REVIEW_F #3): codependent/sbl/labelwrap (defined in §9a)
% has NO ordering rule and needs none.  It depends on
% neither backref/install nor sbl/open: the label-wrap
% machinery only forwards through \codep@orig@label and
% emits its sidecar record at user-call time, never at
% install time.  Documented here so future readers don't
% wonder about the missing rule.

% External ordering: we want to run before hyperref's
% \AtBeginDocument-equivalent hooks wrap \@setref a second
% time.  This rule is best-effort; see the "Load order"
% subsection for the ordering contract with third-party
% packages.
\DeclareHookRule{begindocument/before}%
                {codependent/backref/install}{before}{hyperref}
```

External ordering conflicts (hyperref, `acmart`, `biblatex`)
are a **testing TODO**: until the package has a regression
suite across a matrix of popular preamble stacks, we cannot
claim compatibility by construction.  Users who hit a
conflict should report it along with their full
`\usepackage{...}` list so a targeted `\DeclareHookRule`
can be added.

Notes on the sketch:

- The `\codep@grabfirst` macro is the `\@secondoftwo`-style
  "grab first brace group, throw away the tail up to
  `\@nil`" pattern called for by REVIEW_C finding #1.
  Correct for both the 5-tuple (kernel/modern hyperref) and
  the 2-tuple (pre-2023 hyperref fallback).  For cleveref's
  `<key>@cref` records, the entire record is skipped via
  `\codep@ifcrefkey`.
- `\codep@recordbr` uses `\expandafter\xdef\csname ... brq@N
  \endcsname` — the O(1) append from REVIEW_C finding #2.
  No toks register is touched; no growing `\the` is
  performed.
- `\codep@processbr` uses a *second* csname linked list
  (`codep@brnode@<tgt>@<k>`) for the per-target append.
  The display macro `\codep@br@<tgt>` is only materialised
  lazily by `\codep@collapsebr`, which runs once per
  queried target.  This turns the O(K^2) from REVIEW_C
  finding #11 into O(K).
- Self-ref is checked via `\ifx\codep@tmp@src
  \codep@tmp@tgt` where both are built by `\edef`, so the
  comparison is on the fully expanded display-number
  strings.  REVIEW_C finding #10 is a minor risk around
  brace wrapping; a stricter normaliser can be added later.
- **The `\codep@currentatom` clearing from REVIEW_A
  finding #3 / REVIEW_C finding #4 is handled at the
  atom-end hooks** (not shown in the sketch since it
  belongs in Sections 6 and 7 of `codependent.sty`, not
  Section 8).  See Section 8a.5 below.
- **The `\codep@queuebackref` collapse call** (required
  for `\codep@collapsebr` to ever fire) is not shown in
  the Section 8a.3 sketch because it is a modification to
  an existing macro.  See Section 8a.6 below for the
  concrete edit list.

### Section 8a.5 — `\codep@currentatom` state management

> Upstream motivation: REVIEW_A finding #3 and REVIEW_C
> finding #4.  Promoted from a prose subsection to a
> numbered subsection per REVIEW_D finding #8 so an
> implementer cannot miss it.

The stale-`\codep@currentatom` bug is the single most
impactful correctness hazard in the port.  The package at
`codependent.sty` lines 245, 274, and 399 *sets*
`\codep@currentatom` inside atom-begin hooks but never
*clears* it.  Without the clear, every `\@setref` that
fires between atoms (in a section heading, caption,
footnote, or inter-paragraph remark) is attributed to the
PREVIOUS atom, and the resulting `\codep@atomref` record
points at the wrong source.

#### 8a.5.0 — Timing: why the hook-time `\edef` was wrong

> **Critical correction to v0.1.** The version 0.1 stub at
> `codependent.sty` line 245 contained
> `\edef\codep@currentatom{\theatom}` inside an
> `\AtBeginEnvironment{theorem}` hook body, on the assumption
> that `\refstepcounter{theorem}` had already fired by the time
> the hook ran.  **It had not.**  The triage of REVIEW post-Wave 1
> (2026-04-09) traced the actual timing through etoolbox and
> amsthm and confirmed the opposite: the hook fires *before*
> the counter step.

**Mechanism (cited sources).**

- etoolbox.sty:1803-1824 implements
  `\AtBeginEnvironment{<env>}` via
  `\csgappto{@begin@<env>@hook}`.  The kernel `\begin` macro
  is patched to inject `\csuse{@begin@<env>@hook}` *before*
  calling `\csname<env>\endcsname`.  So the hook body runs in
  the same mouth as `\begin`, **before** the env macro (e.g.
  `\theorem`) is even invoked.
- amsthm.sty:129-149 defines `\@thm`.  The
  `\refstepcounter{#2}` call sits on line 145, deep inside
  `\@thm`, after `\trivlist` setup and style hooks.  The
  caller chain is
  `\begin{theorem}` → `\theorem` → `\@thm{...}{theorem}{...}` →
  ... → `\refstepcounter{theorem}`.  The prepended
  `@begin@theorem@hook` fires strictly **before** this entire
  chain.

**Consequence.**  At hook entry, `\theatom` expands to the
previous atom's display number.  Caching it via `\edef`
(`\edef\codep@currentatom{\theatom}`) freezes the wrong value
into the macro for the rest of the atom's body.  Any
downstream consumer that reads `\codep@currentatom` —
`\codep@writeatomref`, the planned `.sbl` writer, the
backref-display lookup — picks up the wrong number.

Empirical confirmation under the v0.1 stub plus Wave 1's
working aux-write patches:

```
\begin{theorem}\label{thm:A}First.\end{theorem}      % becomes 1.1
\begin{theorem}By \cref{thm:A}, second.\end{theorem} % becomes 1.2
%% expected aux record: \codep@atomref{1.2}{thm:A}
%% actual   aux record: \codep@atomref{1.1}{thm:A}  (off by one)
```

Inside theorem 1's body, the cached `\codep@currentatom` was
observed to be `1.0` — a "ghost atom" number that never
existed in any sense, because the counter step had not yet
fired and `\theatom` therefore returned the pre-section-reset
value.

**Fix (folded into Wave 2's §8a.5 edits).**  Two
complementary changes:

1. **`\codep@writeatomref` reads `\theatom` at write time**,
   not the cached `\codep@currentatom`.  The src argument of
   the emitted `\codep@atomref{<src>}{<tgt>}` record is now
   `\theatom`, which by definition reflects the current
   atom counter state at the moment the `\ref`/`\cref`/etc.
   fires inside the user content — i.e. *after* the
   `\refstepcounter` for the enclosing atom.

2. **`\codep@currentatom` is demoted to an in-atom
   sentinel.**  Its semantics become: empty (`\@empty`) means
   "not currently inside any tracked atom"; any non-empty
   value means "currently inside an atom".  The specific
   value is irrelevant.  The three set sites in Section 6/7
   (theorem hook, proof hook, paragraph hook) can keep their
   existing structure as `\edef\codep@currentatom{\theatom}`
   — the *value* assigned no longer matters, only that it is
   non-empty.  The clear sites (added per the §8a.5 edit list
   below) set it to `\@empty`.

**Why the paragraph-atom and standalone-proof sites are
unaffected.**  Both `\codep@installparahook` (codependent.sty
line ~406) and `\codep@hookproof`'s standalone branch (line
~280) call `\refstepcounter{atom}` *before* the `\edef`, so
their `\theatom` reads were already correct.  They were
accidentally right under the v0.1 misconception.  Only the
theorem hook path (which depends on amsthm's internal
`\refstepcounter` happening later) was broken.

**Why `\codep@queuebackref` callers must also pass
`\theatom`.**  The three call sites at
`\codep@queuebackref{\codep@currentatom}` (codependent.sty
lines 254, 284, 409) currently pass the cached value.  Under
the new sentinel semantics, they must pass `\theatom`
explicitly so the lookup key matches the per-target node
csnames built from `\newlabel` display numbers.  Three-line
edit, included in Wave 2's §8a.5 patch set.

**Latent secondary bug.**  The nest-branch
`\addtocounter{atom}{-1}` at codependent.sty:249 was a v0.1
attempt to "undo" amsthm's `\refstepcounter`.  Under the
correct timing (hook fires *before* the counter step), the
undo decrements a counter that was never advanced.  Wave 2
deletes this line as part of the same fix.

#### Sites that set `\codep@currentatom`

These are the three existing set sites, listed by
`codependent.sty` line number so the patch is unambiguous:

| Line | Site | Current code |
|---|---|---|
| 245 | `\codep@hooktheorem` `AtBeginEnvironment` | `\edef\codep@currentatom{\theatom}` |
| 274 | `\codep@hookproof` `AtBeginEnvironment` standalone | `\edef\codep@currentatom{\theatom}` |
| 399 | `\codep@installparahook` normal branch | `\edef\codep@currentatom{\theatom}` |

#### Sites that must clear `\codep@currentatom`

The three corresponding atom-end sites.  Each clear goes
AFTER the existing `\codep@flushbackref` (so the flush
still reads the correct atom number) and BEFORE the
`\codep@nestlevel` decrement (which restores
pre-environment state).  The concrete edits:

| Line (area) | Site | Patch (insert after flush) |
|---|---|---|
| 249 | `\codep@hooktheorem`'s `AtEndEnvironment` block (after `\codep@flushbackref`) | `\let\codep@currentatom\@empty` |
| 286 | `\codep@hookproof`'s `AtEndEnvironment` block (inside the `\ifbool{codep@proofsnumbered}` conditional, after the flush) | `\let\codep@currentatom\@empty` |
| 460 | `\codep@installparendhook`'s `para/end` hook body (after `\codep@flushbackref`) | `\let\codep@currentatom\@empty` |

#### Why the clear prevents the bug

Section 8a.0's `\@setref` patch guards its `\immediate\write`
on `\ifx\codep@currentatom\@empty`.  With the three clears
in place:

- A `\ref` in a section heading (which runs with
  `\codep@nestlevel > 0` and no atom context) fires
  `\@setref` with `\codep@currentatom` empty; the write is
  skipped; no ghost edge is created.
- A `\ref` in a stray paragraph between a tracked theorem
  and the next atom fires after the theorem's
  `\AtEndEnvironment` has cleared the state; the write is
  skipped; no ghost edge.
- A `\ref` inside a caption or footnote is protected by
  the `\codep@nestlevel` guard AND by the cleared
  `\codep@currentatom` — belt and braces.

#### Cross-cutting consequences

Every site that emits a `.sbl` record (Section 9a's
`\codep@sblwrite@atom` helper) also guards on
`\codep@currentatom`.  Implementing the clear at
atom-end is therefore a prerequisite for both back-ref
correctness (Section 8a) and `.sbl` correctness
(Section 9a) — fix once, benefit twice.

#### Regression test

Add a test case under `tools/codependent/testfiles/` named
`test-stale-currentatom.lvt`.  The fixture:

1. Opens a tracked theorem with `\label{thm:first}`.
2. Closes the theorem.
3. Places a plain paragraph with `\ref{thm:first}` BEFORE
   any new atom starts.
4. Opens a second tracked theorem with `\label{thm:second}`.
5. Asserts via `\codep@debug@aux` (a test helper that
   greps the `.aux`) that NO `\codep@atomref` record names
   `thm:first`'s number as `src` for the stray ref.
   Equivalently, asserts that `thm:second` has no
   "Used in ..." line.

This test pins the three clears in place so an accidental
regression is caught at the `.lvt` level.

### Section 8a.5.a — Detecting restated theorem environments

> Upstream motivation: **REVIEW_E finding #1 (BLOCKER) and
> REVIEW_E Section R.**  The `thmtools` `\restatable` /
> `\restate` mechanism re-fires our
> `\AtBeginEnvironment{theorem}` hook on every restate,
> with `\c@theorem` aliased away from `\c@atom` to a dummy
> counter.  Without a guard, the restated occurrence is
> attributed to whatever atom was current at the restate
> site, the back-reference graph gets ghost edges, and
> the `.sbl` writer emits a duplicate atom record with a
> conflicting type.

The four bugs documented in REVIEW_E Section R:

- **R-1.** On the restate branch, `thm-restate.sty` line 132
  executes `\@xa\let\csname c@#2\endcsname=\c@thmt@dummyctr`,
  breaking the `\c@theorem ↔ \c@atom` alias.  The hook body
  runs in this aliased-away scope.  Even with §8a.5.0's
  read-at-write-time fix in place, any code that observes
  the `\c@theorem` counter directly inside the restate-hook
  body would see the dummy counter, not the live atom
  counter.  The §8a.5.a guard `\ifx\c@theorem\c@atom`
  detects this state and skips the entire hook body on the
  restate branch, so no spurious atom number gets associated
  with the restated theorem and no duplicate
  `\codep@sbl@atom` record is emitted.  (Note: this is a
  separate concern from §8a.5.0's hook-timing fix; the two
  interact but address different defects.)
- **R-2.** amsthm's `\refstepcounter{theorem}` advances
  `\c@thmt@dummyctr` on the restate branch (harmless to
  `\c@atom` since the alias is broken), but our hook
  still calls `\edef\codep@currentatom{\theatom}` which
  confirms the R-1 wrong-number attribution.
- **R-3.** The `.sbl` writer emits a duplicate
  `\codep@sbl@atom{<previous-real-atom>}{theorem}` with
  a conflicting type — the CLI cannot disambiguate.
- **R-4.** `\label` inside the restated body is gobbled
  by `thm-restate`'s `\thmt@gobble@label`, and when
  cleveref is loaded that gobbler takes an optional
  argument — see Section 9a's `\pretocmd{\label}` wrapper
  (fixed under REVIEW_E finding #4 / E#4 below).

See REVIEW_E lines 183-270 and 355-414 for the full
walk of each bug against `thm-restate.sty v0.76` lines
103-184.

#### The fix: `\ifx\c@theorem\c@atom` guard

On the **original** occurrence of a restatable theorem,
`\c@theorem` is still aliased to `\c@atom` by
`\codep@setupcounter` — exactly as it was at
`\codeptrack` time.  On the **restate** occurrence,
`thm-restate.sty` line 132 executes
`\@xa\let\csname c@#2\endcsname=\c@thmt@dummyctr`,
breaking the alias.  The guard at the top of the hook
body therefore distinguishes the two cases with zero
overhead:

```tex
\AtBeginEnvironment{#1}{%
  \ifx\c@theorem\c@atom
    %% Original occurrence: normal hook body.
    ...existing \codep@hooktheorem body...
  \else
    %% Restate occurrence (\c@theorem re-let to dummy):
    %% suppress the whole hook body to avoid
    %%   (a) reading the wrong \theatom,
    %%   (b) writing a duplicate \codep@sbl@atom record,
    %%   (c) queuing back-refs against a stale atom number.
    %% Still bump \codep@nestlevel so inner paragraph
    %% numbering is suppressed inside the restated body
    %% (matching the normal theorem semantics).
    \advance\codep@nestlevel by 1\relax
  \fi
}
\AtEndEnvironment{#1}{%
  \ifx\c@theorem\c@atom
    ...existing \codep@hooktheorem end body...
  \else
    %% Matching end guard for the restate branch.
    \advance\codep@nestlevel by -1\relax
  \fi
}
```

This one-conditional fix closes R-1, R-2, and R-3
simultaneously.  R-4 is addressed separately by E#4
(Section 9a's `\pretocmd{\label}` wrapper needs an
optional-argument variant when cleveref is loaded).

#### Alternative: flag-based gate

The above inlines the guard in both the begin and end
hooks.  An alternative is to set a boolean at begin-time
and read it at end-time:

```tex
\newif\ifcodep@suppressed@hook
\AtBeginEnvironment{#1}{%
  \ifx\c@theorem\c@atom
    \codep@suppressed@hookfalse
    ...normal body...
  \else
    \codep@suppressed@hooktrue
    \advance\codep@nestlevel by 1\relax
  \fi
}
\AtEndEnvironment{#1}{%
  \ifcodep@suppressed@hook
    \advance\codep@nestlevel by -1\relax
  \else
    ...normal end body...
  \fi
}
```

The flag approach is marginally cleaner (the guard logic
exists in one conceptual place) but introduces a new
boolean to maintain across nested theorem environments.
For nested tracked theorems, the flag must be saved and
restored via a stack to avoid clobbering.  **Pick the
inline `\ifx\c@theorem\c@atom` approach** shown above:
the conditional is idempotent against `\c@theorem`
aliasing state, which is the same check at begin and
end, and no stack is required.

#### Save / clear / restore of `\codep@currentatom` on the restate branch

> Upstream motivation: **Section 8a.9 concept-aware
> forward references.**  The inline guard above correctly
> skips the atom-numbering, `.sbl@atom`, and back-ref
> queue work on the restate branch.  But it does NOT
> touch `\codep@currentatom`, which still holds whatever
> value the enclosing context left behind — typically the
> atom number of the intro paragraph that surrounds a
> `\restate{thm:main}` teaser, or of the appendix
> paragraph that surrounds an appendix restate.  Any
> semantic command inside the restated body
> (`\Hom`, `\Hom*`, `\codeptag`, `\label`) would then
> register against that STALE currentatom instead of
> no-op'ing.  For `\Hom*` in particular this is a
> correctness bug: the def site would be recorded as the
> teaser paragraph rather than the original
> `\restatable{theorem}{thm:main}{...}` declaration's
> atom number.

The fix extends the else-branch of the guard with a
save-clear-restore of `\codep@currentatom`.  On restate
begin, save the current value onto a counter-indexed
stack and clear to `\@empty`.  On restate end, pop from
the stack.  The enclosing paragraph's currentatom is
restored verbatim, so nothing outside the restated body
is perturbed.  Inside the restated body, every atom-scoped
emission helper (`\codep@sblwrite@atom`, the
`\Hom`/`\Hom*` dispatcher, the `\label` wrap, the
`\codeptag` macro) guards on
`\ifx\codep@currentatom\@empty` and silently drops — the
restated body becomes a semantic-command no-op zone.

**Why a counter-indexed stack, not a single save slot:**
nested restates (a teaser inside a theorem body that is
itself restated later) must restore in LIFO order.  A
single `\let` save slot would clobber the outer value
when the inner restate begins.  The counter makes the
stack trivially LIFO-correct.

```tex
\newcount\codep@restate@depth
% depth starts at 0; every push increments, every pop
% decrements. The saved value lives at csname
% codep@saved@currentatom@<depth>.

\newcommand*{\codep@pushcurrentatom}{%
  \global\advance\codep@restate@depth1\relax
  \expandafter\xdef
    \csname codep@saved@currentatom@%
      \the\codep@restate@depth\endcsname
    {\codep@currentatom}%
  \global\let\codep@currentatom\@empty}

\newcommand*{\codep@popcurrentatom}{%
  \global\let\codep@currentatom
    \csname codep@saved@currentatom@%
      \the\codep@restate@depth\endcsname
  \global\expandafter\let
    \csname codep@saved@currentatom@%
      \the\codep@restate@depth\endcsname\@undefined
  \global\advance\codep@restate@depth-1\relax}
```

Hook wiring.  The existing else-branch of the theorem
hook becomes:

```tex
\AtBeginEnvironment{#1}{%
  \ifx\c@theorem\c@atom
    %% Original occurrence: normal hook body (unchanged).
    ...existing \codep@hooktheorem body...
  \else
    %% Restate occurrence: guard body + save/clear currentatom.
    \advance\codep@nestlevel by 1\relax
    \codep@pushcurrentatom
  \fi
}
\AtEndEnvironment{#1}{%
  \ifx\c@theorem\c@atom
    ...existing \codep@hooktheorem end body...
  \else
    %% Matching end guard for the restate branch.
    \codep@popcurrentatom
    \advance\codep@nestlevel by -1\relax
  \fi
}
```

The `\codep@pushcurrentatom` call comes AFTER the
nestlevel advance on begin, and `\codep@popcurrentatom`
comes BEFORE the nestlevel decrement on end, so nested
restates see both state pieces in consistent LIFO order.

**Effect on concept registration (cross-reference §8a.9).**
A `\Hom*` call inside a restated body now sees
`\codep@currentatom = \@empty` and silently no-ops —
the concept-def record is NOT written against the
teaser/appendix atom.  The ONLY firing that registers the
def site is the original declaration (first firing, alias
intact, normal hook body), where `\codep@currentatom`
holds the restatable theorem's own atom number.  Teaser
uses of `\Hom` in the intro correctly forward-resolve (at
pass 2 via the concept -> atom map) to the main-body
declaration atom.

**Effect on `\codep@sblwrite@atom` generally.**  Any
`.sbl` record routed through `\codep@sblwrite@atom` —
not just the concept machinery — is dropped inside a
restated body.  `\codep@sbl@label`, `\codep@sbl@use`,
`\codep@sbl@tag`, and a hypothetical future atom-scoped
record all become no-ops on the restate branch.  This is
the intended semantics: the restate is a visual
rerender, not a semantic re-declaration.

#### Regression fixture: `test-restatable.lvt`

```tex
\documentclass{article}
\usepackage{amsthm,thmtools}
\usepackage{codependent}
\newtheorem{theorem}{Theorem}
\codeptrack{theorem}

\begin{document}
\begin{restatable}{theorem}{thmA}\label{thm:A}
  Statement A.
\end{restatable}

\section{Appendix}
A recap follows.  % stray paragraph to advance atom ctr
\restate{thmA}
\end{document}
```

Assertions the fixture must verify:

- `\codep@sbl@atom{<N>}{theorem}` for `thm:A` appears
  **exactly once** in the `.sbl` (the original
  occurrence), never twice.
- The display number printed for `thm:A` on the first
  (original) occurrence matches the display number
  printed on the restate (i.e. `\ref{thm:A}` resolves
  to the same value in both spots).
- No `\codep@atomref` record inside the restated body
  cites the stray paragraph atom as `src`.
- The margin atom number on the section heading
  "Appendix" is absent (verified via PDF text
  extraction; this also exercises E#3).

### Section 8a.6 — Edits to existing `codependent.sty` macros

> Per REVIEW_D finding #5 (BLOCKER): the Section 8a.1-8a.4
> sketch defines new macros but does not specify how the
> existing `codependent.sty` macros interact with them.  An
> implementer who reads only the new sketch will leave
> `\codep@queuebackref` unchanged, never call
> `\codep@collapsebr`, and ship a fully broken port that
> compiles cleanly but renders no "Used in" lines.  This
> subsection enumerates every existing-macro edit needed
> to wire the port end-to-end.

Line numbers are against the current `codependent.sty` (the
one referenced throughout this design doc; 654 lines).

#### 8a.6.a — `\codep@queuebackref` (lines 415-427): REWRITE

Before the existing lookup of `\csname codep@br@#1\endcsname`,
call `\codep@collapsebr{#1}` so that per-target nodes are
lazily materialised on first query.  The collapse macro
itself is idempotent (it short-circuits if the display
csname is already set), so calling it unconditionally on
every `\codep@queuebackref` is fine; subsequent calls for
the same atom number are cheap.

New body:

```tex
\newcommand*{\codep@queuebackref}[1]{%
  \ifbool{codep@backrefs}{%
    \codep@pendingbr={}%
    % Lazy collapse: first call materialises \codep@br@#1.
    \expandafter\ifx\csname codep@brcount@#1\endcsname\relax
      % No refs to this target; collapse is a no-op but
      % still runs to set the empty sentinel.
      \codep@collapsebr{#1}%
    \else
      \codep@collapsebr{#1}%
    \fi
    \@ifundefined{codep@br@#1}{%
      % Still undefined after collapse means the sentinel
      % set it to \empty; treat as no back-refs.
    }{%
      \ifbool{codep@appendix}{}{%
        \codep@pendingbr=\expandafter{%
          \csname codep@br@#1\endcsname}%
      }%
    }%
  }{}%
}
```

Note: `\codep@collapsebr` (defined in Section 8a.3)
already handles both the has-refs and no-refs cases, so
the outer `\ifx\relax` guard in the new body is strictly
redundant — I included it only so the reader can trace the
control flow without jumping back to Section 8a.3.  An
implementer may simplify to a single unconditional
`\codep@collapsebr{#1}` call.

#### 8a.6.b — `\codep@flushbackref` (lines 431-441): MINIMAL EDIT

Unchanged body.  The macro still reads `\codep@pendingbr`
into a temp via `\the`, tests empty, and calls
`\codep@renderinline`.  The token register is populated
from the collapsed display csname in 8a.6.a above, so the
flush mechanism does not need to change.

However, per Section 8a.5, **after** the existing
`\codep@pendingbr={}` reset, ADD:

```tex
  \let\codep@currentatom\@empty
```

This clears the state machine after the flush.  See
Section 8a.5 for the full currentatom edit list.

#### 8a.6.c — `\codep@readsbr` (lines 502-519): DELETE ENTIRELY

The `.sbr` file no longer exists.  The new model reads
`.aux` on pass 2 via LaTeX's normal rerun; there is no
separate `.sbr` to `\IfFileExists` or `\input`.  Delete
the whole `\newcommand*{\codep@readsbr}{...}` block.

Also remove the `\AtBeginDocument{\codep@readsbr}` call
at line 578 (inside `\codeptrack`).

#### 8a.6.d — `\codep@writeauxhash` (lines 523-532): DELETE ENTIRELY

No content hash is written.  `rerunfilecheck` /
`latexmk` handle staleness via the normal
aux-content-changed-between-passes mechanism; the kernel's
"Label(s) may have changed" warning is the only staleness
signal the user needs.

Also remove the `\AtEndDocument{\codep@writeauxhash}`
call at line 580 (inside `\codeptrack`).

#### 8a.6.e — `\codep@auxversion` (lines 537-539): DELETE ENTIRELY

The `\providecommand*{\codep@auxversion}[1]{...}` aux
callback is no longer emitted by any writer, so the
callback has nothing to consume.  Delete.

#### 8a.6.f — `\codep@sbrversion` / `\codep@backref` / `\codep@section` (lines 472-498): DELETE ENTIRELY

These three callbacks existed to consume `.sbr` records.
With the `.sbr` file gone, nothing calls them.  Delete all
three macro definitions.

#### 8a.6.g — Appendix-mode plumbing: KEEP, RE-PLUMB

The appendix machinery is retained but its data source
changes from "accumulated during `\codep@backref`
callbacks" to "walked from per-target `\codep@br@<num>`
csnames at `\codepappendix` call time".

- **`\codep@appendixdata` token register (line 118):**
  KEEP the declaration, but it is no longer populated
  incrementally.
- **`\codep@appendixsection{num}{title}` / `\codep@appendixentry{num}{type}{list}` (lines 616-629):**
  KEEP as-is — they are the rendering primitives.
- **`\codepappendix` (lines 600-612):** REWRITE the body
  to walk the set of known atoms (derivable from the
  `\codep@brnode@*` csname family, or equivalently from a
  list that `codependent.sty` maintains as atoms are created)
  and, for each atom with a non-empty collapsed display
  macro, emit a `\codep@appendixentry`.  Section titles
  come from the TOC entries LaTeX already writes to `.aux`
  (the standard `\contentsline` records).

The rewrite of `\codepappendix` is a ~15-line
single-pass loop; it replaces the token-register
accumulator pattern.  Concrete sketch:

```tex
\newcommand*{\codepappendix}{%
  \ifbool{codep@appendix}{%
    \section*{Dependency Index}%
    \begingroup
      \small
      % Walk \codep@atomlist (a list macro that
      % para/begin, hooktheorem, and hookproof all append
      % to as atoms are created).  Each entry is a
      % (num, type) pair.
      \def\do##1{%
        \codep@appendix@emit##1%
      }%
      \codep@atomlist
    \endgroup
  }{%
    \PackageWarning{codependent}{%
      \string\codepappendix\space ignored: %
      backrefs mode is not 'appendix'}%
  }%
}
\def\codep@appendix@emit#1#2{%
  % #1 = display number, #2 = atom type
  \codep@collapsebr{#1}%
  \expandafter\ifx\csname codep@br@#1\endcsname\@empty\else
    \codep@appendixentry{#1}{#2}{%
      \csname codep@br@#1\endcsname}%
  \fi
}
```

Where `\codep@atomlist` is a new list macro initialised
empty and appended to at every atom-begin site (lines
245, 274, 399).  Append style:

```tex
  \xdef\codep@atomlist{%
    \codep@atomlist
    \do{{\theatom}{<type>}}}
```

The append is O(1) per atom (list grows by one
`\do{...}` entry); the walk at `\codepappendix` call
time is O(N) in the atom count.

#### 8a.6.i — `\codep@suppresssectioning` (lines 349-365): REPLACE WITH KERNEL HOOKS

> Upstream motivation: **REVIEW_E finding #5 (BLOCKER).**
> The current implementation wraps `\@startsection`, which
> is a **no-op under KOMA-Script, memoir, and titlesec**
> because each of those packages replaces `\@startsection`
> at load time with its own dispatcher.  Evidence: titlesec
> lines 1540-1631 install `\ttl@select` and stop calling
> `\@startsection` at typeset time; scrbook.cls lines
> 3506-3530 define `\scr@startsection` as KOMA's
> replacement and sectioning commands route through that,
> not through the kernel `\@startsection`.  KOMA-Script is
> the standard math-monograph class, so this issue affects
> a **majority** of the target audience.

**Delete** the existing `\codep@suppresssectioning`
(`.sty` lines 349-365) which wraps `\@startsection` and
depends on the
`\AddToHook{begindocument/end}{\makeatletter\let\codep@orig@startsection\@startsection\def\@startsection{...}\makeatother}`
pattern.

**Replace** with LaTeX 2021+ generic command hooks on
each sectioning command directly:

```tex
\newcommand*{\codep@suppresssectioning}{%
  \AddToHook{cmd/section/before}[codependent/sectioning]{%
    \global\booltrue{codep@sectioning}}%
  \AddToHook{cmd/subsection/before}[codependent/sectioning]{%
    \global\booltrue{codep@sectioning}}%
  \AddToHook{cmd/subsubsection/before}[codependent/sectioning]{%
    \global\booltrue{codep@sectioning}}%
  \AddToHook{cmd/chapter/before}[codependent/sectioning]{%
    \global\booltrue{codep@sectioning}}%
  \AddToHook{cmd/paragraph/before}[codependent/sectioning]{%
    \global\booltrue{codep@sectioning}}%
  \AddToHook{cmd/subparagraph/before}[codependent/sectioning]{%
    \global\booltrue{codep@sectioning}}%
  \@ifundefined{@makechapterhead}{}{%
    \codep@suppresscmd{\@makechapterhead}%
  }%
  \@ifundefined{@makeschapterhead}{}{%
    \codep@suppresscmd{\@makeschapterhead}%
  }%
}
```

**Why `cmd/<level>/before` works across classes.**
LaTeX 2021+ installs generic command hooks at a layer
below any user-level redefinition of the sectioning
command.  Specifically:

- **titlesec (titlesec.sty lines 1540-1631).**
  titlesec's replacement `\section` is itself defined
  under the kernel's command-hook infrastructure, so
  `cmd/section/before` fires before titlesec's
  `\ttl@select` path.
- **KOMA-Script (scrbook.cls lines 3506-3530).**
  KOMA installs `\scr@startsection` via the very
  same `cmd/@startsection/before` hook mechanism;
  generic per-command hooks work uniformly.
  `cmd/section/before` fires before `\scr@startsection`
  dispatches.
- **memoir.**  Similar pattern to KOMA; the kernel
  `cmd/<level>/before` hook dispatch precedes memoir's
  `\M@sect`.
- **Plain article / book / report classes.**  The
  kernel sectioning commands (which do call
  `\@startsection`) also pass through
  `cmd/<level>/before` first.

The LaTeX 2021+ generic command hooks are a hard
dependency of `codependent.sty` already — the package
requires `[2021/06/01]` in its `\NeedsTeXFormat` line
and uses `\AddToHook{para/begin}` etc.  No new
dependency is introduced.

**`\@makechapterhead` / `\@makeschapterhead`.**  These
are still wrapped via `\codep@suppresscmd` because
they are called from inside `\chapter`'s body after
`cmd/chapter/before` has fired.  `cmd/chapter/before`
sets the flag for the section-title paragraph; the
`\@makechapterhead` wrapper keeps `\codep@nestlevel`
incremented inside the chapter-head block (for
multi-line chapter titles in book classes).

**KOMA verification (REVIEW_F R1 refuted).**  Initial
concern that KOMA-Script might use a renamed
`\scr@makechapterhead` was investigated and refuted:
scrbook.cls line 4132 declares
`\@namedef{@make#1head}{\scr@makechapterhead{#1}}`
with `#1=chapter`, which keeps the kernel name
`\@makechapterhead` live and points it at KOMA's
internal handler.  Our `\@ifundefined{@makechapterhead}`
guard above resolves to "defined" under KOMA and the
wrap installs correctly.  Verified against scrbook.cls
TeX Live 2025.

**`paragraph` / `subparagraph` caveat.**  LaTeX's
`\paragraph` and `\subparagraph` produce inline headings
by default in most classes.  Hooking `cmd/paragraph/before`
catches the heading-paragraph's `para/begin` and sets the
suppress flag.  Some classes (memoir) give
`\paragraph` a display-style layout where the heading
is a separate paragraph, which is also handled
correctly because the flag is set BEFORE the heading's
own `para/begin` fires.

#### 8a.6.j — `trivlist` added to `\codep@installsuppress`

> Upstream motivation: **REVIEW_E finding #7 (MAJOR).**
> amsthm wraps theorem environments in a `trivlist` for
> layout purposes (amsthm.sty line 129: `\@thm` is a
> `\trivlist` wrapper).  Nested-theorem scenarios
> ("definition containing an example") can leave inner
> paragraphs exposed to `para/begin` numbering if
> `trivlist` is not in the suppress list.

In `\codep@installsuppress` (currently `.sty` lines
327-339), add:

```tex
  \codep@suppressenv{trivlist}%
```

Tradeoff: this suppresses paragraph numbering inside any
`trivlist`, not just amsthm's theorem wrappers.  Users
with their own `trivlist`-based environments that they
want numbered as atoms would need a manual re-enable —
but such users are rare, and the amsthm-correctness win
is more important than the theoretical
`\trivlist`-as-atom use case.

**Blast radius (REVIEW_F #4 caveat).**  `\trivlist` is the
underlying primitive for several standard LaTeX2e
environments beyond amsthm's `proof`/`theorem`:

- `center`, `flushleft`, `flushright` (latex.ltx use a
  `trivlist`-based mechanism for centred/flushed blocks)
- `verbatim` (the kernel implementation wraps in a
  `trivlist`)
- `quotation`, `quote`, `verse` (also `trivlist`-based
  in many class implementations)
- amsmath display environments do NOT use `trivlist`
  (they use `array`/`tabular` internals)
- `enumerate`, `itemize`, `description` are `list`,
  not `trivlist`, and are suppressed separately

In practice this is the **correct behaviour** for a
Pavlov-style atom-numbering setup: a paragraph inside a
`center` block, a `flushright` byline, or a `verbatim`
code listing should NOT be a separately-numbered atom.
But the breadth is worth documenting for users debugging
"why is this paragraph not numbered?" — the answer is
usually "it's inside a `trivlist`".

**Future-work API (TODO).**  If a real use case for
`\trivlist`-based numbered content appears, expose
`\codepuntrack{trivlist}` (or a per-use `\codepatom`
explicit-marker command).  Not in v1; flagged so the
implementer remembers the option exists.

**Why this doesn't double-suppress the theorem body.**
`\codep@hooktheorem`'s begin body already increments
`\codep@nestlevel` for the theorem environment
(`codependent.sty` line 243).  The `\trivlist` suppression
is additive: on theorem begin, nestlevel is incremented
once by the theorem hook and once by the trivlist
hook, so inside the body nestlevel is 2.  On theorem
end, both are decremented and nestlevel returns to 0.
Correct either way — `para/begin` suppresses iff
`nestlevel > 0`.

Add a regression fixture:
`testfiles/test-amsthm-nested.lvt` exercising a
`theorem` containing a nested `lemma` with a paragraph
between, and asserting the atom count.

#### 8a.6.k — `enumitem` `\newlist` auto-registration

> Upstream motivation: **REVIEW_E finding #10 (MINOR).**
> `enumitem`'s `\newlist{name}{base}{levels}` creates
> user-defined list environments that escape our default
> suppression list (which only names `enumerate`,
> `itemize`, `description`).

Inside the `begindocument/before` install path (or inside
`\codep@installsuppress`), add:

```tex
\@ifpackageloaded{enumitem}{%
  \let\codep@orig@newlist\newlist
  \def\newlist#1#2#3{%
    \codep@orig@newlist{#1}{#2}{#3}%
    \codep@suppressenv{#1}%
  }%
}{}
```

`\newlist`'s signature is verified against
enumitem.sty line 1730: three mandatory arguments,
`{name}{base}{levels}`.  No optional arguments.  The
wrapper forwards the call to enumitem's original
`\newlist` (which creates the environment) and then
suppresses the freshly-created environment name.

Install after enumitem has loaded, which means the
wrapper install site is `begindocument/before` (not
package-load time, because enumitem may load after
codependent).

Regression fixture: `testfiles/test-enumitem-newlist.lvt`.

#### 8a.6.l — `tcolorbox` / `mdframed` suppression

> Upstream motivation: **REVIEW_E finding #13 (MINOR).**
> Both packages create boxed-content environments that
> naturally contain paragraphs; those paragraphs should
> not become atoms.

In `\codep@installsuppress`, conditionally suppress
these environments only if the respective package is
loaded:

```tex
\AddToHook{begindocument/before}[codependent/suppress/boxes]{%
  \@ifpackageloaded{tcolorbox}{%
    \codep@suppressenv{tcolorbox}%
  }{}%
  \@ifpackageloaded{mdframed}{%
    \codep@suppressenv{mdframed}%
  }{}%
}
```

Note that `tcolorbox` also supports user-defined
variants via `\newtcolorbox{myname}{...}`.  Parallel to
`\newlist` above, the long-term fix is to wrap
`\newtcolorbox` to auto-register the new environment;
for v0.1 that is deferred.  Users with custom tcolorbox
variants must manually call
`\codepsuppress{myname}` after `\newtcolorbox`.

Regression fixture: `testfiles/test-tcolorbox.lvt`.

#### 8a.6.m — Summary of additions vs. deletions

| Kind | Lines added | Lines deleted |
|---|---|---|
| New (Section 8a.0-8a.4, 8a.7, helpers) | ~200 | — |
| `\codep@queuebackref` rewrite (8a.6.a) | ~15 | 13 |
| `\codep@flushbackref` edit (8a.6.b) | 1 | 0 |
| `\codep@readsbr` deletion (8a.6.c) | 0 | 18 |
| `\codep@writeauxhash` deletion (8a.6.d) | 0 | 10 |
| `\codep@auxversion` deletion (8a.6.e) | 0 | 3 |
| `\codep@sbrversion` / `@backref` / `@section` deletion (8a.6.f) | 0 | 27 |
| `\codepappendix` re-plumb (8a.6.g) + `\codep@atomlist` plumbing | ~25 | ~13 |
| currentatom clears (Section 8a.5) | 3 | 0 |
| `\restatable` guard (Section 8a.5.a, E#2) | ~20 | 0 |
| `\codep@suppresssectioning` replacement (8a.6.i, E#3) | ~20 | 17 |
| `trivlist` suppress (8a.6.j, E#7) | 1 | 0 |
| `enumitem \newlist` wrap (8a.6.k, E#10) | ~8 | 0 |
| `tcolorbox` / `mdframed` suppress (8a.6.l, E#13) | ~8 | 0 |
| **Total** | **~301** | **~101** |

Net change: roughly **+200 lines** on the current
`codependent.sty`, bringing it from ~654 to ~854.  The
REVIEW_E fixes add ~60 lines beyond the REVIEW_D
baseline, primarily in the three-site reference
interception (Section 8a.0) and the `\restatable`
guard (Section 8a.5.a).  Section 8a.9 (concept-aware
forward references) adds another ~40 lines of .sty
code on top of that baseline.

### Section 8a.9 — Concept-aware forward references

> Upstream motivation: **user direction 2026-04-09,
> post-v1.0-test.**  In any serious math paper, the
> introduction and early sections routinely mention
> terminology and symbols BEFORE they are formally
> defined.  Auto-backref schemes that pick "first
> occurrence wins" as the defining site produce WRONG
> backref graphs on ~90% of real papers.  Pavlov's
> manual marking of the defining site was a feature, not
> a kludge.  This subsection specifies the `\Hom*`
> starred-variant machinery that lets the author mark
> the def site explicitly and lets the `.sty` resolve
> forward references correctly in pass 2 without CLI
> involvement.

#### The forward-reference problem

Concrete example.  Consider the opening of a category-
theory monograph:

```latex
\section{Introduction}
In this paper we study the $\Hom{X}{Y}$ functor of
objects in a \textbf{category}. This will be made
precise in \cref{sec:categories}.

\section{Categories}\label{sec:categories}
\begin{definition}
  A \textbf{category} consists of objects and
  morphisms, with a $\Hom{X}{Y}$ set for each pair.
\end{definition}

Later, in any chapter: "the $\Hom{A}{B}$ set..."
```

The `\Hom` command fires THREE times.  The first firing
is in the intro (a forward gesture), the second is in
the definition (the true defining site), the third is a
backward-pointing use.  A naive "first occurrence wins"
rule would pick the intro as the defining site — wrong —
and every subsequent use, including the actual
definition firing, would back-reference to the intro
paragraph.  On a typical 300-page monograph this is
wrong for 90%+ of concepts.

The ONLY signal the tool has to distinguish a forward
gesture from a definition is the author's intent.  There
is no lexical hint.  The author must mark explicitly.

#### User API: star dispatch inside `\codepnewcommand`

`\codepnewcommand{\Hom}[2]{body}` now defines TWO
variants of the command for the price of one
declaration:

- `\Hom{A}{B}` — normal use.  Typesets the body, emits
  a `\codep@sbl@use` record and a `\codep@conceptref`
  aux record under the current atom.
- `\Hom*{A}{B}` — defining-site marker.  Typesets the
  body IDENTICALLY to the unstarred form; the star is
  purely metadata saying "this atom is the defining
  site for concept `Hom`".  Emits a `\codep@sbl@def`
  record and a `\codep@concept` aux record.

Exactly ONE `\Hom*` call per defined concept is
permitted (enforced by error).  Zero `\Hom*` calls plus
any `\Hom` uses is a warning (concept backrefs
disabled).  See "Error handling" below.

The same dispatch applies to `\codepNewDocumentCommand`:
a star is prepended to whatever argspec the user
supplies, and the wrapped command dispatches on
`\IfBooleanTF`.  See §9a's implementation sketch.

Author source looks like:

```latex
\codepnewcommand{\Hom}[2]{\mathrm{Hom}(#1,#2)}

\section{Introduction}
We study the $\Hom{X}{Y}$ functor...     % use, forward

\section{Categories}
\begin{definition}
  The $\Hom*{X}{Y}$ set is defined as...  % def site
\end{definition}

Later: $\Hom{A}{B}$...                    % use, backward
```

All three `\Hom` uses — the two non-star uses and the
one star use — typeset to the same visual output.  The
difference is purely in the backref metadata.

#### Architecture: observation layer, NOT backref injection

Concept-tracking records are written to BOTH sidecars.
Each sidecar serves a different consumer:

- **`.aux`** (read by `codependent.sty` itself at pass 2).
  Two record types (`\codep@concept`, `\codep@conceptref`)
  allow the .sty to create hyperlinks from concept uses
  back to their definition sites.  Concept edges do
  **NOT** appear in "Used in" lists — those are reserved
  for explicit `\ref`/`\cref` citations only.  The
  `.aux` concept records exist solely for hyperlink
  resolution.
- **`.sbl`** (read by the semantic CLI, Layer 2).  One
  new record type (`\codep@sbl@def`) gives the CLI
  source-location-grounded concept def sites; the
  existing `\codep@sbl@use` record is reused for
  non-star concept uses.  The CLI can build a richer
  concept graph with source locations, JSON exports,
  dot renderings, and whatever else Layer 2 wants to
  do — but the .sty's typeset output is independent of
  whether the CLI ever runs.

**Concept edges are NOT injected into the backref pipeline.**
The previous design (Option C hybrid) fed concept edges
into `\codep@recordbr` / `\codep@appendbr`, causing concept
uses to appear in "Used in" lists alongside explicit
`\ref` citations.  This was removed: "Used in" shows only
explicit cross-references.  Concept dependency analysis is
the CLI's responsibility (Layer 2).

This separation is deliberately simpler than the hybrid
approach.  Each sidecar is self-sufficient
for its own consumer.

#### New `.aux` records

Two new record types.  Both are `\providecommand`-safe
no-ops at package load so that reading a pre-existing
`.aux` on pass 1 (when the real callbacks are not yet
defined) is harmless.  On pass 2 the real callbacks are
installed at `\AtEndPreamble` — the same hook site as
the existing `\@setref`/`\cref@getlabel` patches in
§8a.0 — before LaTeX's `\@input{\jobname.aux}` fires at
`\begin{document}`.

```tex
% Written by \Hom*  (emitted via \codep@emit@def).
\codep@concept{Hom}{<def-atom-num>}

% Written by \Hom (emitted via \codep@emit@use).
\codep@conceptref{<use-atom-num>}{Hom}
```

Package-load-time no-op defaults (in `codependent.sty`'s
startup code, before any `.aux` is read):

```tex
\providecommand*{\codep@concept}[2]{}
\providecommand*{\codep@conceptref}[2]{}
```

Real callbacks (installed at `\AtEndPreamble` / hook
`begindocument/before`, labelled `codependent/backref/install`
for ordering; see §8a.7):

```tex
\AddToHook{begindocument/before}[codependent/concept/install]{%
  % Concept def-site map: csname codep@conceptdef@<name>
  % holds the atom number of the def site.
  \def\codep@concept##1##2{%
    \@ifundefined{codep@conceptdef@##1}%
      {\expandafter\gdef
         \csname codep@conceptdef@##1\endcsname{##2}}%
      {% Second def record for same concept from aux.
       % This can happen if the author is editing and a
       % stale aux record lingers; prefer the latest
       % firing (overwrite).  The in-TeX emitter
       % \codep@emit@def catches the duplicate at
       % source-emit time via the same csname check and
       % issues the PackageError there; by the time the
       % aux is read, a duplicate can only come from a
       % stale prior-run aux, which will be refreshed
       % on the next pass.  Overwrite silently at
       % aux-read time.
       \expandafter\gdef
         \csname codep@conceptdef@##1\endcsname{##2}}%
  }%
  % Concept use: feed the edge into the existing backref
  % defer queue.  The src atom is ##1 (the atom where
  % \Hom fired); the target atom is the def atom stored
  % under csname codep@conceptdef@##2.  If the def
  % site is not yet known at aux-read time (forward
  % reference on a missing def), the resolve call
  % defers to a second-pass retry: we push a pending
  % record into \codep@conceptpending and retry after
  % the full aux read completes.
  \def\codep@conceptref##1##2{%
    \@ifundefined{codep@conceptdef@##2}%
      {% Def site not yet seen in this aux read.  It
       % may appear later in the same aux (the aux is
       % not sorted by document order after the first
       % pass).  Push onto the pending list and retry
       % at \AtBeginDocument.
       \g@addto@macro\codep@conceptpending{%
         \codep@resolveconcept{##1}{##2}}}%
      {\codep@resolveconcept{##1}{##2}}%
  }%
  % The resolver feeds a resolved (src, tgt) edge into
  % the existing \codep@recordbr linked-list queue
  % from §8a.1.  The target is the def atom's number,
  % looked up in the concept map.
  \def\codep@resolveconcept##1##2{%
    \edef\codep@tmp@tgt{%
      \csname codep@conceptdef@##2\endcsname}%
    \codep@recordbr{##1}{\codep@tmp@tgt}%
  }%
}
\gdef\codep@conceptpending{}
```

The pending-list retry handles the case where the aux
file order does not match document order — specifically,
the case where a `\codep@conceptref` record is read
before its matching `\codep@concept` record.  This can
happen because LaTeX's aux file is written in the order
the aux-writing calls fire during typesetting; if a
forward-ref use (intro) precedes the def site (§3) in
source order, the `.aux` will have the `\codep@conceptref`
line BEFORE the `\codep@concept` line.  On a first
aux-read pass we cannot resolve; we defer to the pending
queue and flush at `\AtBeginDocument`, by which time the
full aux has been read and the concept map is complete.

The flush is a simple expansion of the saved pending
list:

```tex
\AddToHook{begindocument/end}[codependent/concept/flush]{%
  \codep@conceptpending
  \global\let\codep@conceptpending\@empty
}
```

The resolved edges feed into `\codep@recordbr` exactly
like the edges from `\@setref`, `\cref@getlabel`, and
`\HyRef@autosetref`.  Downstream, `\codep@flushbrqueue`
and `\codep@collapsebr` (§8a.1, §8a.3) do not care
whether an edge came from a `\ref`, a `\cref`, or a
concept resolution — they all flow through the same
per-target linked list and the same "Used in X, Y"
display path.

#### New `.sbl` records

One new record type, plus reuse of an existing one.

```
\codep@sbl@def{<atom>}{Hom}     % NEW: emitted by \Hom*
\codep@sbl@use{<atom>}{Hom}     % EXISTING: emitted by \Hom
```

`\codep@sbl@def` is a new record added to the §9a
schema table.  It is atom-scoped (routed through
`\codep@sblwrite@atom`).  It has the same shape as
`\codep@sbl@use` (two arguments: atom number, concept
name) but different semantics — `def` is the unique
def site, `use` is any (non-star) use.

The existing `\codep@sbl@use` record is **reused
verbatim** for non-star `\Hom` uses.  No schema change
to `@use` itself; the CLI already parses it and builds
per-command use lists.  What the CLI now additionally
consumes is the `\codep@sbl@def` record, which lets
it mark the def-site atom specifically.  For any
concept `C`, the CLI computes:

- `def_site(C)` = the unique `\codep@sbl@def{_}{C}`
  record's atom number (or warning/error per below).
- `use_sites(C)` = all `\codep@sbl@use{_}{C}` records'
  atom numbers.

This gives a per-concept def/use split without any new
parsing machinery beyond the one-line addition of the
`@def` record type to the CLI's grammar.

#### Pass-2 concept resolution (walkthrough)

1. **Pass 1.** User's `\Hom*` fires inside the
   definition environment.  At emit time,
   `\codep@emit@def` writes
   `\codep@concept{Hom}{<def-atom>}` to the current
   `.aux` file and `\codep@sbl@def{<def-atom>}{Hom}`
   to the `.sbl`.  User's `\Hom` uses (intro and
   later) each fire `\codep@emit@use`, which writes
   `\codep@conceptref{<use-atom>}{Hom}` to aux and
   `\codep@sbl@use{<use-atom>}{Hom}` to sbl.  Pass 1
   finishes with aux containing all these records.
2. **Pass 2 preamble.** `codependent.sty` is loaded.  The
   `\providecommand*{\codep@concept}[2]{}` defaults
   install so that if the aux is read early for any
   reason, the records are harmless no-ops.  At
   `\AtEndPreamble`, the `codependent/concept/install` hook
   runs and replaces the no-op defaults with the real
   callbacks above.  Ordering rule (§8a.7):
   `codependent/concept/install` fires AFTER
   `codependent/backref/install` but BEFORE the aux read at
   `\@input{\jobname.aux}`.
3. **Pass 2 aux read.** LaTeX's `\@input{\jobname.aux}`
   runs inside `\document`.  Every `\codep@concept`
   call populates the concept map
   `\csname codep@conceptdef@<name>\endcsname`.  Every
   `\codep@conceptref` call either resolves immediately
   (if the def record has already been seen during this
   aux read) or pushes onto `\codep@conceptpending`
   for the end-of-read flush.
4. **Pass 2 begindocument/end flush.** The pending list
   is expanded.  Each deferred `\codep@resolveconcept`
   looks up the now-complete concept map and feeds the
   resolved edge into `\codep@recordbr`.  The linked-
   list defer queue from §8a.1 holds the edges until
   the per-target `\codep@collapsebr` is called at
   each def atom's "Used in" display site.
5. **Pass 2 typeset.** The def atom's "Used in X, Y"
   list now naturally includes the atom numbers of
   every `\Hom` use in the document — both forward-
   pointing (intro) and backward-pointing (later
   sections) — because they all resolved to the same
   def atom and all flowed through the same backref
   display pipeline.

#### Error handling

- **Missing def site** (`\Hom` used but no `\Hom*`
  anywhere in the document).  Detected at
  `\AtEndDocument` by scanning the concept-use set
  against the concept-def map.  Action:

  ```tex
  \ifcodep@conceptwarnings
    \PackageWarning{codependent}{%
      \string\Hom\space used N times but no
      \string\Hom*\space definition site found;
      backrefs for \string\Hom\space are disabled}%
  \else
    \PackageInfo{codependent}{%
      \string\Hom\space used N times but no
      \string\Hom*\space definition site found;
      backrefs for \string\Hom\space are disabled
      (conceptwarnings=off)}%
  \fi
  ```

  No fallback to first-occurrence (explicitly rejected
  by user as 90% wrong).  The concept's use records
  still appear in the `.sbl`, and the CLI can mark the
  concept as "undefined" in its own output, but the
  `.sty` typeset PDF has no "Used in" line at any atom
  for this concept.  Exit code is 0 (warning, not
  error) — the document still compiles and renders.

  **Quiet mode for smoke-test workflows.**  When the
  package option `conceptwarnings=off` is in effect,
  the missing-def-site detection still runs but emits
  via `\PackageInfo` instead of `\PackageWarning`.
  The `.log` still records which concepts have no def
  site (so a CLI / test runner can post-process the
  info lines), but the standard `Warning|Error` grep
  used by test runners no longer fires.  This mode is
  intended for the real-world arxiv corpus under
  `tools/codependent/testfiles/real-world/`, where
  wrappers mechanically rewrite the paper's
  `\newcommand`s into `\codepnewcommand`s but cannot
  insert `\Hom*` markers (which would require domain
  knowledge of which atom is the canonical definition).
  For hand-authored documents, leave this option at
  its default value `on`.

- **Duplicate def site** (`\Hom*` fires twice or more,
  at different atoms).  Detected in `\codep@emit@def`
  via `\@ifundefined{codep@concept@Hom}`: if already
  defined, error and halt:

  ```tex
  \PackageError{codependent}{%
    \string\\Hom* defined at atoms X and Y}{%
    Exactly one definition site is permitted per
    concept.  Use \string\\Hom\space (without star) at
    the non-definitional site.}
  ```

  This halts the build.  The author must resolve the
  ambiguity: either one of the two atoms is the "real"
  def site and the other should drop its star, or the
  author has two definitions that should be two
  separately-named concepts.

  Implementation note: the check uses
  `\@ifundefined{codep@concept@Hom}` where
  `codep@concept@Hom` is a csname set the first time
  `\codep@emit@def` fires for `Hom`.  On subsequent
  firings the csname is already defined, triggering
  the error branch.  This is a TeX-time check, not a
  pass-2 aux-read check: the error fires during pass 1
  at the second `\Hom*` invocation's typeset time.

- **Def site in empty-currentatom context** (`\Hom*`
  fires with `\codep@currentatom = \@empty`, e.g.,
  inside a footnote, caption, or orphaned paragraph
  that codependent does not track).  Silent no-op.  The
  author may legitimately have `\Hom*` inside a
  footnote or caption where atom numbering is
  suppressed; in that case there is no atom to register
  against.  The concept will later trigger the
  "missing def site" warning above if any `\Hom` use
  exists, which correctly surfaces the problem to the
  author without false-alarm errors from the footnote.

- **Def site inside a restated body** (`\Hom*` inside
  `\restate{thm:main}`).  Silent no-op by construction:
  the extended §8a.5.a guard saves and clears
  `\codep@currentatom` on the restate branch, so
  `\codep@emit@def` sees the empty currentatom and
  takes the silent-no-op branch above.  The original
  declaration firing (where `\Hom*` lives in the
  restatable body with the counter alias still intact)
  is the one that registers the def site.  See
  "Interaction with restatable" below.

#### Interaction with `\codep@currentatom` clearing (cross-reference §8a.5)

§8a.5 clears `\codep@currentatom` at every atom-end
site (theorem end, proof end, paragraph end) and after
the three-site reference-interception helpers run.
This is what makes the "empty-currentatom silent no-op"
branch of the emit helpers meaningful: a `\Hom*` or
`\Hom` call that fires in a section heading, caption,
or inter-paragraph remark sees the cleared currentatom
and correctly drops the record rather than registering
against whatever atom happened to precede the
orphaned call.

The concept machinery inherits this correctness for
free — it uses the same `\codep@currentatom` guard
pattern as every other atom-scoped emitter in §9a.

#### Interaction with restatable (cross-reference §8a.5.a)

§8a.5.a's extended guard saves and clears
`\codep@currentatom` at the start of a restated
theorem body and restores it at the end.  Inside the
restated body, every semantic-command emitter sees the
empty currentatom and no-ops.  Consequences:

- **Intro-teaser pattern.**  Author writes
  `\restate{thm:main}` in the introduction as a teaser,
  containing `\Hom*` inside the restated body.  The
  restate branch of the theorem hook clears
  currentatom; `\Hom*` sees empty and no-ops; the
  teaser does NOT register a def site.  Later, when
  `\restatable{theorem}{thm:main}{body with \Hom*}`
  fires in the main body for the first time (alias
  intact, normal hook body), `\Hom*` sees the main-body
  atom as currentatom and registers that atom as the
  def site.  Result: `\Hom` forward-references from
  the intro correctly resolve to the main-body atom.
- **Appendix-restate pattern.**  The opposite: the
  `\restatable{theorem}{thm:main}{body with \Hom*}` is
  in the main body (declaration fires, registers def
  site), and `\restate{thm:main}` in the appendix
  silently no-ops the `\Hom*` inside the restated body.
  Again, the def site is the main-body declaration
  atom.  Backward uses from main and forward uses from
  intro both resolve correctly.
- **Nested restates.**  The depth counter in §8a.5.a
  ensures LIFO-correct restore even when a restated
  body itself contains a nested restate.

In both patterns, the author writes `\Hom*` exactly
once (inside the theorem body they intend to restate),
and the combination of the §8a.5.a guard and the
§8a.9 emit helpers ensures the def site is registered
against the original declaration's atom — never
against the teaser or appendix invocation atom.

#### Implementation sketch

The TeX-time emit helpers and the pass-2 aux callbacks
are shown in §9a's implementation sketch for
`\codepnewcommand` (the `\codep@emit@def` /
`\codep@emit@use` helpers) and in the
`codependent/concept/install` hook code block above
(the `\codep@concept` / `\codep@conceptref` aux
callbacks and the pending-list retry).  See those
code blocks for the full detail.

The split is:

- **§9a sketch.** Per-command machinery: how a
  `\codepnewcommand`-defined macro dispatches on the
  star, how emit-time records are written to aux and
  sbl, how duplicate def sites and empty-currentatom
  contexts are handled.
- **§8a.9 sketch (this section).** Pass-2 aux-read
  machinery: how the concept map is populated, how
  forward references are deferred, how resolved edges
  feed into `\codep@recordbr`.

Both sides are ~20 lines of TeX each.  The split
mirrors the existing design: §9a owns the user API and
the declaration-time wrappers, §8a owns the backref
pipeline and the aux-read callbacks.

The package option is implemented in codependent.sty's
existing pgfkeys block (Section 3) by adding:

```tex
  conceptwarnings/.is choice,%
  conceptwarnings/on/.code =
    {\booltrue{codep@conceptwarnings}},%
  conceptwarnings/off/.code =
    {\boolfalse{codep@conceptwarnings}},%
  conceptwarnings/.default = on,%
```

with the corresponding boolean declaration in Section 4
(Internal state):

```tex
\newbool{codep@conceptwarnings}
\booltrue{codep@conceptwarnings}
```

The boolean must be declared before the pgfkeys block
references it.  The `\ifcodep@conceptwarnings` branch
in the `\AtEndDocument` scan (see Error handling above)
is the only call site.

#### Regression fixtures

Five fixtures under `tools/codependent/testfiles/unit/`,
each pinning a distinct correctness case of the
concept machinery.  See the fixture files themselves
for header metadata and assertion specifics:

| Fixture | Tests |
|---|---|
| `test-concept-forward-ref.lvt` | Basic `\Hom` in intro + `\Hom*` in later definition; aux/sbl records; forward resolution |
| `test-concept-def-site-required.lvt` | `\Hom` used with no `\Hom*`: warning, no crash |
| `test-concept-duplicate-def-site.lvt` | Two `\Hom*` calls: error, build halts |
| `test-concept-in-restatable-intro-teaser.lvt` | `\Hom*` inside `\restate{thm:main}` teaser in intro; def site must be main-body declaration, not intro |
| `test-concept-in-restatable-appendix.lvt` | `\Hom*` inside main-body `\restatable{theorem}{thm:main}{...}`; `\restate` in appendix; def site must be main-body declaration, not appendix |

All five fixtures FAIL today (the concept machinery is
unimplemented); they turn green as §8a.9 lands in
`codependent.sty`.

### Load order

`codependent.sty` **must be loaded after `hyperref` and after
`cleveref` (if either is used)**.  This has always been
required because `hyperref` redefines `\@setref`; the
requirement is strengthened in the port because the
`\newlabel` override at `\AtEndPreamble` must see the
final definitions of `\newlabel` / `\newlabelxx`.

The install point is `\AtEndPreamble` (equivalently
`begindocument/before` with an explicit ordering label).
**Do NOT use `\AtBeginDocument` for the override.**
`\AtBeginDocument` fires AFTER LaTeX reads `.aux` (at
line ~9489 of `latex.ltx`, the `\@input{\jobname.aux}`
inside `\document`), which is AFTER we needed the override
to be in effect.  The override's whole purpose is to
intercept aux records as they are read; if it is installed
after the read, every record is missed.

The queue flush is a separate hook at `begindocument/end`,
which fires after the aux read has populated the queue
via the `\codep@atomref` callbacks.  Ordered `before` `*`
so that other packages' `\AtBeginDocument` hooks see a
populated `\codep@br@<num>` namespace.

### Performance

Per REVIEW_C finding #2, the **rejected** approach is
dpmac's token-register defer queue.  At 15 000 cross
references, a toks-register append of an existing
`\the\codep@brqueue` is O(k) per append, giving O(N^2/2)
total token copies.  At ~30 tokens per record and ~75 ns
per token copy, that is:

| Refs | Token copies | Rejected toks approach |
|---|---|---|
| 2 000 | ~60 M | ~4.5 s |
| 15 000 | ~3.4 B | **~253 s** (4 minutes) |
| 100 000 | ~150 B | ~3.1 hours |

The **accepted** approach (Section 8a.1 above) uses a
csname linked list: each `\codep@recordbr` is O(1)
(one `\xdef` and one counter bump), the flush is O(N)
total, and the per-target collapse is O(K) per target
(not O(K^2)).  Realistic timings:

| Refs | Accepted linked-list approach |
|---|---|
| 2 000 | ~0.01 s |
| 15 000 | **~0.08 s** |
| 100 000 | ~0.5 s |

The 15 000-ref figure is the target for a multi-hundred
page research monograph.  The 100 000-ref figure is a
worst-case encyclopedia and is still well inside
interactive build budget.

**Per-`\cref` amplification (per REVIEW_E finding #2).**
With the three-patch design of Section 8a.0, a cref list
`\cref{thm:A,thm:B,thm:C}` fires `\cref@getlabel` once
per label — three times for this example.  Each call
issues one `\codep@writeatomref`, so a single cref
command writes K records where K is the list length.
At pass 2 the downstream dedup in `\codep@processbr`
collapses these correctly: each (src, tgt) edge is
recorded once via the consecutive-dedup gate.  The
overhead is therefore K aux-write calls per cref list
(bounded by LaTeX's `\protected@write` cost, ~microseconds
each) and zero additional work in the flush.  For a
document with 5 000 cref lists averaging K=3 labels, the
extra aux-write cost is ~15 000 writes ~= 50ms of build
time — imperceptible.  The `.aux` file is roughly 2x
larger in the cref-heavy case compared to a plain-`\ref`
document, but still tiny relative to the typeset content.

**Hash-table saturation at very large scale (per REVIEW_D
finding #13).** At ~100 000 atoms, TeX's csname hash table
(default ~15 000 strings) saturates and lookup degrades.
Each `\codep@brnode@<tgt>@<k>` and each
`\codep@br@<num>` lives in that hash table, so a worst-
case document with 100 000 atoms and 100 000 backref
edges allocates ~200 000 csnames.  Users on documents
that large must increase `hash_extra` (and possibly
`pool_size`) in `texmf.cnf`, or accept that csname
lookups slow down as the hash overflows.  This is a TeX
engine limitation inherited by all heavy csname-based
machinery, not a codependent bug.  For documents up to ~30 000
atoms (the practical ceiling of even very large
monographs) the default hash table is fine.  Document in
the user-facing README when one exists.

### Queue flush timing

LaTeX's `\begin{document}` expands `\document`, which at
line ~9489 of `latex.ltx` executes
`\@input{\jobname.aux}` to read the aux file in-place.
`\AtBeginDocument` hooks fire at line ~9512, AFTER the aux
read completes.  Therefore:

- The `\newlabel` override must be installed **before**
  line ~9489.  `\AtEndPreamble` (equivalently
  `begindocument/before`) is the correct pin.
- The queue flush must run **after** line ~9489 but
  preferably before other `\AtBeginDocument` hooks run,
  so that third-party hooks can read the populated
  `\codep@br@*` namespace.  `begindocument/end` is the
  correct pin, declared `before` `*` via
  `\DeclareHookRule` (LaTeX 2021+).  This is the pattern
  REVIEW_C finding #8 asks for and is already in the
  implementation sketch above.

If LaTeX 2021+ hook rules are unavailable (shouldn't
happen — the package already requires `[2021/06/01]`),
fall back to `\AtBeginDocument` without a rule.  The
flush is still correct; only third-party ordering is
weakened.

### Edge cases

Known issues, each with a one-line mitigation drawn from
the review record:

- **Stale `\codep@currentatom` between atoms** (REVIEW_A
  #3 / REVIEW_C #4): clear at atom-end in Sections 6/7;
  guard at every write site.  See the "currentatom
  clearing" subsection above.
- **Label between two atoms**: resolves to whichever
  counter `\refstepcounter` last advanced, which is
  LaTeX's normal semantics; the atom `\label` attaches to
  is correct by construction when inside a tracked atom.
- **Nested refs inside `\label` arguments**: out of scope;
  authors who do this have bigger problems.
- **Self-ref detection** via `\ifx` on `\edef`'d display
  numbers: sufficient for byte-equal cases; fails only on
  brace-wrapped variants (REVIEW_C #10) which is a minor
  visual bug and can be tightened with a normaliser.
- **Refs in captions / footnotes**: suppressed because
  `\codep@nestlevel > 0` at those sites, so
  `\codep@currentatom` is not written to.
- **Cleveref `<key>@cref` records**: skipped by the
  `\codep@ifcrefkey` filter (REVIEW_C #12); the real
  record for the same key (without suffix) is used.
- **pre-2023 hyperref `\newlabelxx` pathway** (REVIEW_C
  #3): patched alongside `\newlabel` in
  `\codep@installnewlabel`.
- **Kernels older than `\AddToHook`**: the package already
  errors out at `codependent.sty` line 636-642.
- **Restated theorems via `\restatable` / `\restate`**
  (REVIEW_E #1): detected by `\ifx\c@theorem\c@atom`
  guard at the top of `\codep@hooktheorem`'s begin/end
  hooks.  See Section 8a.5.a.
- **`\@startsection`-wrapping classes (KOMA, memoir,
  titlesec)** (REVIEW_E #5): suppression now uses
  `cmd/<level>/before` generic hooks instead of a
  `\@startsection` wrapper.  See Section 8a.6.i.
- **Inline `\tikz` / `\tikzcd` inside atom bodies**
  (REVIEW_E #9): see "Recommended preamble snippets"
  below.
- **cref lists `\cref{a,b,c}` producing K aux-writes**:
  the downstream `\codep@processbr` dedup absorbs the
  multiplicity; see Section 8a.0 "Why so many patch
  sites?" for details.

### Recommended preamble snippets (REVIEW_E #9)

> Upstream motivation: **REVIEW_E finding #9 (MINOR).**
> The user targets category-theory monographs that use
> `tikzcd` heavily for diagrams.  Inline
> `\tikz[baseline]{...}` and `\tikzcd[...]{...}` inside
> paragraph bodies can cause `para/begin` to fire inside
> the diagram's internal node structure, producing
> spurious atom numbers.

The default `\codep@installsuppress` covers the
`tikzpicture` environment (when tikz is loaded), but
**inline** forms are commands, not environments, and
must be registered via `\codepsuppresscmd`.  Add to
your preamble, AFTER `\usepackage{tikz}` /
`\usepackage{tikz-cd}` and AFTER `\usepackage{codependent}`:

```latex
% If you use inline tikz or tikzcd in atom bodies,
% suppress para/begin inside them so nodes do not become
% sub-atoms:
\codepsuppresscmd{\tikz}
\@ifpackageloaded{tikz-cd}{%
  \codepsuppresscmd{\tikzcd}%
}{}%
```

For users who define their own tikz wrapper macros
(e.g., `\newcommand{\smallcd}[1]{\begin{tikzcd}[...]#1\end{tikzcd}}`),
the underlying environment is already suppressed, so no
additional action is needed.  For wrappers that use
inline `\tikz{...}` form, add
`\codepsuppresscmd{\smallcd}` after the definition.

Similar wrappers for the other MINOR-class compatibility
issues:

```latex
% tcolorbox / mdframed environments (auto-suppressed when
% the package is loaded; see Section 8a.6.l).  User
% variants created via \newtcolorbox need manual
% registration:
\newtcolorbox{mybox}{...}
\codepsuppress{mybox}

% enumitem \newlist variants are auto-suppressed via the
% \newlist wrapper installed in Section 8a.6.k; no
% action needed.

% Custom verbatim wrappers (listings, minted user
% environments) should be suppressed manually:
\lstnewenvironment{mylisting}{...}{...}
\codepsuppress{mylisting}
```

These snippets are optional for users who do not use
the corresponding packages.  The core codependent.sty
package imposes no hard dependencies on tikz,
tcolorbox, mdframed, listings, or enumitem.

### Regression fixtures (consolidated)

New regression fixtures introduced by REVIEW_D and
REVIEW_E, in addition to the existing
`test-basic`/`test-backrefs`/`test-options`/etc. set.
Each fixture lives under `tools/codependent/testfiles/`
and runs under `l3build check`.

| Fixture | Tests | Source finding |
|---|---|---|
| `test-stale-currentatom.lvt` | Stray ref between atoms does not write ghost edge | REVIEW_A #3 / REVIEW_C #4 (MAJOR) |
| `test-cleveref.lvt` | `\cref{thm:A}` produces a back-ref edge | REVIEW_E #2 / E#1 (BLOCKER) |
| `test-hyperref-autoref.lvt` | `\autoref{thm:A}` and `\ref*{thm:A}` produce edges | REVIEW_E #2,#3 / E#1,E#5 (BLOCKER/MAJOR) |
| `test-restatable.lvt` | `\restatable` + `\restate` does not double-emit atom | REVIEW_E #1 / E#2 (BLOCKER) |
| `test-koma-titlesec.lvt` | `scrbook` section heading is NOT numbered as atom | REVIEW_E #5 / E#3 (BLOCKER) |
| `test-amsthm-nested.lvt` | Nested theorem gets one atom number, not three | REVIEW_E #7 / E#7 (MAJOR) |
| `test-cleveref-label-opt.lvt` | `\label[theorem]{thm:A}` optional arg works | REVIEW_E #4 / E#4 (MAJOR) |
| `test-equations-shared-align.lvt` | Documents per-line counter-advance hazard | REVIEW_E #6 / E#6 (MAJOR) |
| `test-enumitem-newlist.lvt` | `\newlist`-created environments auto-suppressed | REVIEW_E #10 / E#10 (MINOR) |
| `test-ntheorem.lvt` | ntheorem backend works (verifies DESIGN.md claim) | REVIEW_E #12 / E#12 (MINOR) |
| `test-tcolorbox.lvt` | `tcolorbox` environment is suppressed | REVIEW_E #13 / E#13 (MINOR) |
| `test-latexml.lvt` | LaTeXML binding emits stable CSS classes | REVIEW_D LaTeXML test / E#11 |

**Test infrastructure helpers.** Several fixtures need a
small `\codep@debug@aux` macro (greps the current
`.aux` file from inside `l3build check`) and a way to
extract PDF text for the section-heading-not-numbered
check.  Both are standard `l3build` patterns; no
custom tooling required.

**Running the suite.** `l3build check` from
`tools/codependent/` runs every `.lvt` in `testfiles/`.
Fixtures that depend on optional packages (cleveref,
hyperref, KOMA, etc.) should `\RequirePackage` with
`\@ifpackageloaded` guards or use `l3build`'s
per-fixture support-file mechanism to declare package
dependencies.

### License note

The whole of `codependent.sty` is distributed under **GNU GPL
version 3** as a derivative work of `dpmac.tex`.  The
Section 8a port brings in the defer-queue /
`\processbackref` / `\predefbackref` pattern and the
two-register structure; those are the derivative elements.
Downstream users must retain GPLv3 obligations when
redistributing `codependent.sty` as part of a larger work.
See `tools/codependent/CREDITS.md` for the provenance
table and the intent to reach out to Pavlov about a
possible LPPL dual-license courtesy.

## Section 8b — LaTeXML HTML rendering

### Problem

LaTeXML renders `\codep@renderinline`'s
`\rightline{\small\sffamily Used in X, Y.}` as
presentational HTML with no semantic class — typically a
generic `<ltx:text>` wrapper that loses the "this is a
back-reference block" information at the XML/HTML boundary.
Consumers of the HTML output (the mwablab web site, any
external reader) cannot then hide, style, or collapse
back-reference blocks via CSS because there is no stable
selector to target.  The same problem applies to the
superscript atom margin numbers emitted by
`\codep@emitmargin`.

The Section 8a back-reference *graph computation* is
unaffected by this — LaTeXML honours LaTeX's `.aux` rerun
semantics, so the same queue-flush dance in Section 8a
runs during LaTeXML processing, and
`\codep@br@<num>` csnames become populated exactly as they
do under pdflatex.  Only the **rendering** step has a
LaTeXML-specific wrinkle, and only because LaTeXML's
default bindings for `\rightline` and `\textsuperscript`
emit presentational markup.

### Solution

Ship a **LaTeXML binding file** `codependent.ltxml` alongside
`codependent.sty` in the CTAN package.  The binding is written
in Perl against the LaTeXML `Package` API and overrides
exactly two rendering macros — `\codep@renderinline` and
`\codep@emitmargin` — to emit semantic HTML spans with
stable class names.  Users of pdflatex, lualatex, or
xelatex see no change; only the LaTeXML processing
pipeline picks up the override.

### Stable class contract

`codependent.sty` promises the following CSS class names as a
**public interface**.  Downstream HTML consumers may rely
on these class names being stable across codependent.sty
versions; additions are allowed, renames and removals are
breaking changes.

| Class | Wraps |
|---|---|
| `codependent-usedby` | The entire "Used in X, Y." block |
| `codependent-usedby-label` | The leader text "Used in" |
| `codependent-usedby-list` | The comma-separated ref list |
| `codependent-usedby-ref` | Each individual back-ref anchor |
| `codependent-usedby-trailer` | The trailing period |
| `codependent-atomnum` | The superscript atom number in the margin |
| `codependent-atomnum-value` | The numeric text inside the atom number |

`codependent.sty` **does not ship CSS**.  The web toolchain
(currently the mwablab site generator) supplies the
stylesheet.  A one-line `.codependent-usedby { display: none; }`
hides all back-references; `.codependent-usedby { display:
block; }` shows them.  Authors who want collapsible
disclosure can wrap the block in `<details>` via a tiny
post-processing step or via CSS `content:` tricks; that is
out of scope for `codependent.sty` itself.

### Reference `codependent.ltxml` sketch

```perl
# -*- mode: Perl -*-
# codependent.ltxml -- LaTeXML binding for codependent.sty
# Copyright 2026, GNU GPL v3.  Part of the codependent package.
#
# Graph computation is done by codependent.sty via LaTeX's
# normal .aux rerun, which LaTeXML honours.  This file
# only redefines the RENDERING macros so HTML output
# carries semantic class names.

package LaTeXML::Package::Pool;
use strict;
use warnings;
use LaTeXML::Package;

# ---- "Used in X, Y." block ---------------------------------

DefMacro('\codep@renderinline{}',
  '\lxML@codep@renderinline{#1}');

DefConstructor('\lxML@codep@renderinline{}',
    "<ltx:text class='codependent-usedby'>"
  . "<ltx:text class='codependent-usedby-label'>Used in </ltx:text>"
  . "<ltx:text class='codependent-usedby-list'>#1</ltx:text>"
  . "<ltx:text class='codependent-usedby-trailer'>.</ltx:text>"
  . "</ltx:text>");

# ---- Margin atom number ------------------------------------

DefMacro('\codep@emitmargin{}',
  '\lxML@codep@atomnum{#1}');

DefConstructor('\lxML@codep@atomnum{}',
    "<ltx:text class='codependent-atomnum'>"
  . "<ltx:text class='codependent-atomnum-value'>#1</ltx:text>"
  . "</ltx:text>");

# ---- .sbl / \codeptag / \codepnewcommand etc. -----------
#
# These produce no typeset output under pdflatex (they are
# write-only sidecar records -- see Section 9a).  Under
# LaTeXML we also want them to produce no HTML, so we
# define them as no-ops on the typeset side.  The .sbl
# file is still written because LaTeXML honours
# \immediate\write.
DefMacro('\codeptag{}{}', '');
# \codepnewcommand and \codepNewDocumentCommand are
# handled in the .sty itself (not in this file) because
# their wrappers must generate TeX tokens to define the
# wrapped command at LaTeXML parse time.  LaTeXML honours
# \newcommand and \NewDocumentCommand normally, so the
# wrapped commands will exist and behave correctly under
# LaTeXML once their bodies are emitted.

1;
```

**Handling `#1` inside the "Used in" list.**  The list is a
tokenised sequence of `\hyperlink{...}{num}` calls (from
Section 8a), which LaTeXML's hyperref binding already
turns into `<ltx:ref>` elements.  The outer
`codependent-usedby-list` span is sufficient to address those
via the CSS selector `.codependent-usedby-list > ltx:ref`.

**Per-anchor `codependent-usedby-ref` class (per REVIEW_D
finding #12).**  An explicit per-anchor class is
implementable via a scoped `\hyperlink` override in
`codependent.ltxml`.  The override is gated on a state flag
that `\lxML@codep@renderinline` raises on entry and
clears on exit, so it is active only inside a "Used in"
list and harmless to other `\hyperlink` uses elsewhere in
the document:

```perl
# In codependent.ltxml, alongside the binding above:

DefMacro('\codep@usedby@begin', '');
DefMacro('\codep@usedby@end',   '');

# Track whether we are inside a "Used in" list.  LaTeXML
# state via AssignValue / LookupValue.
DefPrimitive('\codep@usedby@begin', sub {
  AssignValue('codep@usedby@active' => 1, 'global'); });
DefPrimitive('\codep@usedby@end', sub {
  AssignValue('codep@usedby@active' => 0, 'global'); });

# Wrap the renderinline DefConstructor so the begin/end
# fire around the list.
DefConstructor('\lxML@codep@renderinline {}',
  "<ltx:text class='codependent-usedby'>"
  . "<ltx:text class='codependent-usedby-label'>Used in </ltx:text>"
  . "<ltx:text class='codependent-usedby-list'>"
  . "?&codependent_usedby_open()(#1)?&codependent_usedby_close()"
  . "</ltx:text>"
  . "<ltx:text class='codependent-usedby-trailer'>.</ltx:text>"
  . "</ltx:text>");

# Override \hyperlink only when the flag is set.
DefConstructor('\hyperlink {} {}',
  sub {
    my ($document, $key, $text) = @_;
    if (LookupValue('codep@usedby@active')) {
      $document->openElement('ltx:ref',
        labelref => ToString($key),
        class    => 'codependent-usedby-ref');
      $document->absorb($text);
      $document->closeElement('ltx:ref');
    } else {
      # Default behaviour: hand off to LaTeXML's stock
      # \hyperlink binding (do not collide).
      Digest(T_CS('\@codep@hyperlink@orig')
        . T_BEGIN . $key->unlist . T_END
        . T_BEGIN . $text->unlist . T_END);
    }
  });
```

The exact LaTeXML idiom for "fall through to the kernel
binding" varies by LaTeXML version; the comment "do not
collide" flags that the implementer must consult LaTeXML
docs for the current invocation pattern.  The shape above
is illustrative.  An alternative simpler approach: skip
the override entirely and rely on `.codependent-usedby-list >
ltx:ref` CSS selectors, which works with zero `.ltxml`
complexity.

### Cross-reference to `.sbl` and the semantic CLI

`.sbl` records, `\codeptag`, and `\codepnewcommand` /
`\codepNewDocumentCommand` metadata do
**not** need LaTeXML bindings, because they produce no
typeset output.  They are write-only sidecar data consumed
by `codependent-cli` (Layer 2).  LaTeXML processes `.tex`
source to produce HTML; it has no reason to see `.sbl`.
The semantic CLI is the thing that reads `.sbl`, and it
never emits HTML directly in the current design — though
a future phase may produce HTML fragments for concept
index pages.  That is out of scope for Section 8b.

### File layout update

Add `codependent.ltxml` to `tools/codependent/`:

```
tools/codependent/
  codependent.sty              the package
  codependent.ltxml            LaTeXML binding (Section 8b)
  CREDITS.md              GPLv3 notice for the dpmac port
  DESIGN.md               this file
  ...
```

`codependent.ltxml` is part of the CTAN-publishable package and
ships alongside `codependent.sty` in the same directory.  Both
files fall under the same GPLv3 license.

### Testing strategy

Add a test item `test-latexml.lvt` (or equivalent golden
fixture under `testfiles/`) that:

1. Runs LaTeXML on a tiny document with a tracked theorem
   and a single `\ref` back into it.
2. Greps the generated XML for the expected class
   structure: `class="codependent-usedby"`,
   `class="codependent-usedby-label"`, and
   `class="codependent-atomnum"` must all be present.
3. Runs under the project's test harness alongside the
   pdflatex-based golden tests.

LaTeXML outputs XML (not HTML directly); an xmllint or
ripgrep check is sufficient to assert the class hooks are
emitted.

**Pre-commit validation (per REVIEW_D finding #11).**
Before committing `codependent.ltxml`, run

```
latexml --dest=/tmp/out.xml testfiles/test-minimal.tex
```

on a minimal fixture document.  LaTeXML reports
`DefMacro` / `DefConstructor` argument-pattern errors
loudly at parse time (e.g. "Missing argument count",
"Unbalanced braces in pattern"), so a successful run is
strong evidence the binding is at least syntactically
valid.  This check is cheap and should be wired into
`l3build check` once the LaTeXML binding lands.

### Non-goals for Section 8b

- Does **not** ship CSS or JavaScript.
- Does **not** define UI behaviour (collapsible, tooltip,
  sidebar).
- Does **not** replace the standard LaTeXML pipeline; it
  augments a small number of macro bindings.
- Does **not** attempt to render the `.sbl` file as HTML;
  that is the semantic CLI's concern (and not part of the
  current CLI scope either).
- Does **not** change Section 8a.  The back-reference
  graph is computed in TeX regardless of output engine.

## Section 9a — Semantic sidecar (.sbl) writer

### Purpose

`.sbl` is a write-only sidecar file that `codependent.sty`
emits during pass 1 (and every subsequent pass) alongside
the standard `.aux`.  Its purpose is to give Layer 2 (the
semantic CLI) enough per-atom context to analyse the
document without re-tokenising the `.tex` source from
scratch to find atom boundaries.  The `.sty` never reads
`.sbl` — it is strictly one-way output for downstream
semantic tools.

`.sbl` does **not** duplicate anything LaTeX already writes
to `.aux`.  Labels are the one borderline case: the `.aux`
has `\newlabel{key}{{num}...}` entries already, but the
`.sbl` ALSO emits `\codep@sbl@label{num}{key}` records so
that the CLI can read atom-scoped cross-references without
parsing `.aux` at all.  This redundancy is deliberate and
documented.

### Location fallback for `.sbl` records

`.sbl` records include a location (atom number) so the CLI
knows where each event occurred.  The location is determined
by this fallback chain:

1. **`\codep@currentatom`** (atom number) — when inside a
   tracked theorem, proof, or numbered paragraph.
2. **Finest sectioning level** (`\thesubsubsection` >
   `\thesubsection` > `\thesection`) — when outside an
   atom (e.g. `paragraphs=off` and in running text).

The CLI can distinguish atom-level locations (e.g. `2.1`)
from section-level locations by the record context or by a
prefix/flag in the location field (design TBD).

**Rationale:** with `paragraphs=off`, concept uses in running
text between theorems have no atom identity.  Dropping these
records entirely loses dependency information the CLI needs.
A section-level fallback preserves coarse but usable location
context: "concept Hom used somewhere in section 1.3."

This fallback applies ONLY to `.sbl` records.  The "Used in"
display in the PDF is atom-only — section-level locations do
not appear in backref lists.

### Record format

Line-oriented.  One call to a `\codep@sbl@*` control
sequence per line.  Keys are pure ASCII; values are UTF-8.
Per **REVIEW_C finding #6**, the format is **flattened**:
no comma-separated key-value blobs.  Each metadata pair is
a dedicated record with a fixed number of brace-delimited
arguments.  The CLI parses N `{}`-groups and stops.

```
\codep@sbl@version{1}
\codep@sbl@source{main.tex}
\codep@sbl@atom{1.2.3}{paragraph}
\codep@sbl@meta{1.2.3}{src}{main.tex:42:1}
\codep@sbl@atom{1.2.4}{Definition}
\codep@sbl@meta{1.2.4}{src}{main.tex:48:1}
\codep@sbl@meta{1.2.4}{env}{definition}
\codep@sbl@label{1.2.4}{def:category}
\codep@sbl@label{1.2.4}{def:cat-alias}
\codep@sbl@tag{1.2.4}{uid}{cat:category}
\codep@sbl@tag{1.2.4}{introduces}{Hom}
\codep@sbl@tag{1.2.4}{introduces}{id}
\codep@sbl@tag{1.2.4}{type}{Cat}
\codep@sbl@use{1.2.5}{Hom}
\codep@sbl@use{1.2.5}{circ}
\codep@sbl@cmddef{Hom}{kind}{newcommand}
\codep@sbl@cmddef{Hom}{arity}{2}
\codep@sbl@cmddef{Hom}{src}{main.tex:15:1}
\codep@sbl@cmddef{Cite}{kind}{NewDocumentCommand}
\codep@sbl@cmddef{Cite}{argspec}{s o m}
\codep@sbl@cmddef{Cite}{src}{main.tex:18:1}
\codep@sbl@end{OK}
```

**Record types.**

| Macro | Arity | Meaning |
|---|---|---|
| `\codep@sbl@version{v}` | 1 | File format version. Current: `1`. |
| `\codep@sbl@source{file}` | 1 | Master source file name. |
| `\codep@sbl@atom{num}{type}` | 2 | Atom begins. `type` is `paragraph`, `Definition`, `Theorem`, `proof`, etc. |
| `\codep@sbl@meta{num}{k}{v}` | 3 | Per-atom metadata pair. Keys: `src` (file:line:col), `env`, `depth`. Extensible. |
| `\codep@sbl@label{num}{key}` | 2 | Each `\label{key}` inside atom `num`. |
| `\codep@sbl@tag{num}{kind}{value}` | 3 | User `\codeptag{kind}{value}` record. Free-form. |
| `\codep@sbl@use{num}{cmd}` | 2 | Invocation of a `\codepnewcommand`/`\codepNewDocumentCommand`-wrapped command inside atom `num`. |
| `\codep@sbl@cmddef{cmd}{k}{v}` | 3 | Command-definition metadata (one record per property). Keys: `kind` (always present, value `newcommand` or `NewDocumentCommand`), `arity` (integer, only when `kind=newcommand`), `argspec` (xparse string, only when `kind=NewDocumentCommand`), `src` (always present). NOT per-atom; global. |
| `\codep@sbl@end{OK}` | 1 | Sentinel at `\AtEndDocument`. |

**End marker** (per REVIEW_C finding #7).  The **last line**
of a complete `.sbl` file is `\codep@sbl@end{OK}`,
written from the `\AtEndDocument` hook.  Presence of this
line is the CLI's test for "complete file"; absence means
pdflatex was killed or crashed mid-run and the CLI must
treat the sidecar as stale and warn.  (The CLI should NOT
attempt to recover partial `.sbl` data; that is a recipe
for silently analysing 70% of a document and producing
misleading reports.)

### Open timing

**Per REVIEW_C finding #5**, the `.sbl` stream is opened at
`\AtEndPreamble` (equivalently `begindocument/before`
with an explicit ordering label).  **Not** at
`\AtBeginDocument`.

Why `\AtEndPreamble`: user documents may contain atoms
inside their own `\AtBeginDocument` blocks (e.g.,
frontmatter definitions, preface theorems injected by a
class or by user glue code).  `\AtBeginDocument` hooks
fire in registration order, and there is no guarantee
that `codependent.sty`'s hook runs before a user hook that
emits an atom.  If the stream is opened at
`\AtBeginDocument`, the first atom emitted from any
earlier-registered user hook sees `\codep@sblwrite` as a
no-op and is silently dropped from the sidecar.

At `\AtEndPreamble`, the preamble has finished but no
`\AtBeginDocument` hook has fired yet, so the open always
precedes every atom write.

```tex
\AddToHook{begindocument/before}[codependent/sbl/open]{%
  \if@filesw
    \newwrite\codep@sblout
    \immediate\openout\codep@sblout=\jobname.sbl\relax
    \global\booltrue{codep@sblopen}%
    \immediate\write\codep@sblout{%
      \string\codep@sbl@version{1}}%
    \immediate\write\codep@sblout{%
      \string\codep@sbl@source{\jobname.tex}}%
  \fi
}
% The explicit ordering rule is declared once, centrally, in
% Section 8a.7 (hook installation).  See that section for
% the internal ordering between codependent/backref/install and
% codependent/sbl/open, and the external rule against hyperref.
```

#### biblatex hook ordering (REVIEW_E #8)

> Upstream motivation: **REVIEW_E finding #8 (MINOR).**
> biblatex writes extensive `\abx@aux@*` records to `.aux`
> via `begindocument/before`-adjacent hooks.  Our `.sbl`
> writer does NOT collide with these (different
> namespace), but the relative ordering of
> `codependent/sbl/open` and biblatex's own install hooks is
> not pinned.

Our existing ordering rule (`codependent/backref/install`
declared `before` `hyperref`, and `codependent/sbl/open`
declared `after` `codependent/backref/install` — see Section
8a.7) places our install chain at the front of the hook
firing order, which is safe against biblatex because
biblatex does not depend on our csname namespace and we
do not read biblatex's `\abx@aux@*` records.  The
ordering is effectively "codependent fires first, biblatex
fires later" — the natural order, with no conflict.

If a future biblatex release installs a hook that
collides with our label/ref machinery (e.g., wraps
`\newlabel` in a way that breaks our
`\codep@installnewlabel` override chain), add:

```tex
\@ifpackageloaded{biblatex}{%
  \DeclareHookRule{begindocument/before}%
    {codependent/backref/install}{after}{biblatex}%
}{}
```

to the Section 8a.7 hook rules.  Unnecessary for current
biblatex releases; document for forward-compat.

### Close timing

At `\AtEndDocument`: write the `\codep@sbl@end{OK}`
sentinel, then `\closeout` the stream.

```tex
\AtEndDocument{%
  \ifbool{codep@sblopen}{%
    \immediate\write\codep@sblout{%
      \string\codep@sbl@end{OK}}%
    \immediate\closeout\codep@sblout
    \global\boolfalse{codep@sblopen}%
  }{}%
}
```

If `\AtEndDocument` never runs (crash, kill -9,
`\errmessage` abort), the sentinel is absent and the CLI
rejects the file on the next analysis run.

### Emission points

At each hook site in `codependent.sty`, the following records
are written.  All calls go through the guarded helper
`\codep@sblwrite@atom` (see "Guard pattern" below), which
checks `\codep@currentatom` before emitting atom-scoped
records.

> **Note (per §8a.5.0).**  Atom-scoped emission helpers must
> pass `\theatom` (not the cached `\codep@currentatom`
> sentinel) when the record's payload includes the atom
> display number, e.g.
> `\codep@sbl@atom{\theatom}{paragraph}`.  The
> `\codep@sblwrite@atom` guard still uses
> `\ifx\codep@currentatom\@empty` to gate emission on "in
> tracked atom" — only the *value* of the atom number is
> read fresh from `\theatom` at emit time.

| Hook site (in `codependent.sty`) | Records emitted |
|---|---|
| `\codep@hooktheorem`, `\AtBeginEnvironment{<env>}` after setting `\codep@currentatom` | `\codep@sbl@atom{num}{<env>}` + `\codep@sbl@meta{num}{env}{<env>}` + `\codep@sbl@meta{num}{src}{<file:line:col>}` |
| `\codep@hookproof`, `\AtBeginEnvironment{proof}` standalone branch | `\codep@sbl@atom{num}{proof}` + `\codep@sbl@meta{num}{src}{...}` |
| `\codep@installparahook`, normal paragraph branch after `\refstepcounter` | `\codep@sbl@atom{num}{paragraph}` + `\codep@sbl@meta{num}{src}{...}` |
| `\label` wrap (new site; cleveref-aware, see "Label wrap: cleveref optional argument" below) | `\codep@sbl@label{num}{key}` — one per `\label` call inside a current atom |
| `\codeptag{kind}{value}` | `\codep@sbl@tag{num}{kind}{value}` |
| `\codepnewcommand{\cmd}[n]{...}` (definition time) | `\codep@sbl@cmddef{cmd}{kind}{newcommand}` + `\codep@sbl@cmddef{cmd}{arity}{n}` + `\codep@sbl@cmddef{cmd}{src}{...}` — NOT atom-scoped (global record) |
| `\codepNewDocumentCommand{\cmd}{spec}{...}` (definition time) | `\codep@sbl@cmddef{cmd}{kind}{NewDocumentCommand}` + `\codep@sbl@cmddef{cmd}{argspec}{spec}` + `\codep@sbl@cmddef{cmd}{src}{...}` — NOT atom-scoped |
| Wrapped command (either kind), every invocation inside an atom | `\codep@sbl@use{num}{cmd}` |

The `src` metadata is built from LaTeX's
`\currfilename`, `\the\inputlineno`, and a column counter
(column counter may be approximate or omitted in the v1
writer; the `:0` suffix means "unknown column").

### Label wrap: cleveref optional argument (REVIEW_E #4)

> Upstream motivation: **REVIEW_E finding #4 (MAJOR).**
> cleveref's `\label` accepts an optional `[type]`
> argument, and `thm-restate.sty` line 182 redefines
> `\thmt@gobble@label` to accept one too when cleveref
> is loaded.  A naive `\pretocmd{\label}{...}` swallows
> the optional argument and either errors or emits a
> corrupted `\codep@sbl@label{num}{[type]key}` record.

The label wrap must detect the optional argument.  The
pattern uses `\@ifnextchar[` plus two helper macros,
one for each branch.  Install at
`begindocument/before` (after cleveref has loaded if
present), not at package-load time:

```tex
%% ------------------------------------------------------------
%% Section 9a emission: \label wrap (cleveref-aware).
%% Called from the begindocument/before install hook after
%% cleveref has had its chance to redefine \label.
%% ------------------------------------------------------------
\AddToHook{begindocument/before}[codependent/sbl/labelwrap]{%
  \let\codep@orig@label\label
  \@ifpackageloaded{cleveref}{%
    %% cleveref path: \label[type]{key}, where [type] is optional.
    \def\label{%
      \@ifnextchar[%]
        \codep@sbl@label@withopt
        \codep@sbl@label@noopt
    }%
  }{%
    %% No cleveref: \label{key} only.
    \def\label##1{%
      \codep@sblwrite@atom{%
        \string\codep@sbl@label
          {\codep@currentatom}{##1}}%
      \codep@orig@label{##1}%
    }%
  }%
}

\def\codep@sbl@label@withopt[#1]#2{%
  \codep@sblwrite@atom{%
    \string\codep@sbl@label
      {\codep@currentatom}{#2}}%
  \codep@orig@label[#1]{#2}%
}

\def\codep@sbl@label@noopt#1{%
  \codep@sblwrite@atom{%
    \string\codep@sbl@label
      {\codep@currentatom}{#1}}%
  \codep@orig@label{#1}%
}
```

**What the wrapper preserves and how the double-wrap works
(REVIEW_F #1 clarification):**

Our wrapper is installed at `begindocument/before`.  At
that point cleveref has NOT yet installed its own `\label`
wrapper (cleveref does that inside its own
`\AtBeginDocument`, which fires later than
`begindocument/before`).  So when we capture
`\codep@orig@label`, it is the **kernel**
`\label`/`\@newl@bel` pair, not cleveref's wrapper.

When cleveref's `\AtBeginDocument` runs later, cleveref
captures the current `\label` (which is OUR wrapper) and
installs its own outer wrapper around it.  At user-call
time, cleveref's outer wrapper fires first, processes the
optional argument, then forwards the mandatory key to its
captured target — which is our dispatcher.  Our
dispatcher's `\@ifnextchar[` then sees no bracket
(cleveref already stripped it) and falls through to the
no-optional-arg branch, emitting
`\codep@sbl@label{num}{key}` with the correct mandatory
key and forwarding to the kernel `\label` via
`\codep@orig@label`.

Net effect:

```
user: \label[type]{key}
  -> cleveref's outer wrap: strips [type], records r@key@cref
       -> codependent's wrap: emits .sbl record with `key`
            -> kernel \label: writes \newlabel{key}{...}
```

Cleveref's `\newlabel{key@cref}{...}` write still happens
in cleveref's outer layer.  Our `.sbl` record fires from
our middle layer.  The kernel `\newlabel{key}{...}` write
happens from the bottom layer.  All three artifacts land
correctly.

- The `.sbl` record always emits only the label KEY
  (`#2` in the cleveref-direct-call branch, `##1` in the
  no-cleveref branch), never the `[type]` optional
  argument — the CLI does not need the type hint because
  it can derive the type from the enclosing atom's own
  metadata.

**`\@ifnextchar[` lookahead caveat (REVIEW_F #2).**
Our dispatcher's `\@ifnextchar[` peeks at the token stream
AFTER the mandatory argument has been consumed.  If a user
writes pathological source like
`\label[theorem]{thm:A}[some stuff]` (where `[some stuff]`
is an unrelated bracket group following the label),
codependent's dispatcher would consume `[some stuff]` as a
spurious optional argument.  This is theoretical only —
no real document writes this — but it is documented here
for completeness alongside the `\hyperref[label]{text}`
deliberate-uncovered note in §8a.0.

**Interaction with `\restatable` (REVIEW_E Section R,
bug R-4).**  On the restate branch of a restatable
theorem, `thm-restate.sty` line 135 aliases
`\label` to `\thmt@gobble@label` (which itself is
redefined at line 182 to accept a 2-arg `[o m]` form
when cleveref is loaded).  Our `\pretocmd`-like wrapper
is installed BEFORE thm-restate's alias fires (because
we install at `begindocument/before` and thm-restate
dispatches its alias inside the restate branch at
typeset time).  Under the `\restate`, `\label` is
`\thmt@gobble@label`, not our wrapped version — so
we do NOT emit a duplicate `\codep@sbl@label` record
on the restate.  This is the correct behaviour
(REVIEW_E Section R marks R-4 as "not actually a bug"
for precisely this reason: the restate occurrence is
a visual rerender, not a new label site).

#### Regression fixture: `test-cleveref-label-opt.lvt`

```tex
\documentclass{article}
\usepackage{amsthm}
\usepackage{cleveref}
\usepackage{codependent}
\newtheorem{theorem}{Theorem}
\codeptrack{theorem}

\begin{document}
\begin{theorem}
  \label[theorem]{thm:A}
  Statement A with a cleveref-typed label.
\end{theorem}

Later, \cref{thm:A} is referenced.
\end{document}
```

Assertions:

- `.sbl` contains `\codep@sbl@label{<N>}{thm:A}`
  (KEY only, no brackets, no `[theorem]` prefix).
- `.aux` contains both the kernel `\newlabel{thm:A}{...}`
  and cleveref's `\newlabel{thm:A@cref}{...}`.
- The `\cref{thm:A}` back-reference edge is correctly
  recorded (closes the loop with E#1).

### Guard pattern

All emission points route through one of two helpers.
Atom-scoped records (everything except `\codep@sbl@cmddef`)
use `\codep@sblwrite@atom`, which drops the write if
`\codep@currentatom` is empty:

```tex
\newcommand*{\codep@sblwrite}[1]{%
  \ifbool{codep@sblopen}{%
    \immediate\write\codep@sblout{#1}%
  }{%
    % Should be impossible once the file is opened at
    % begindocument/before.  Log once for debugging.
    \codep@sblwrite@warnonce
  }%
}

\newcommand*{\codep@sblwrite@atom}[1]{%
  \ifx\codep@currentatom\@empty
    % Orphan: not inside an atom context.  Drop per
    % REVIEW_C finding #4.
  \else
    \codep@sblwrite{#1}%
  \fi
}
```

Global records (`\codep@sbl@cmddef`) bypass the
atom guard and go through `\codep@sblwrite` directly.
The `\codep@sblwrite@warnonce` branch exists to catch
the debugging nightmare REVIEW_C finding #5 calls out;
under normal operation it should never fire because the
stream is opened at `\AtEndPreamble`.

### User API: `\codeptag`

One new public command is added to the `.sty`'s user API:

```tex
\newcommand*{\codeptag}[2]{%
  \codep@sblwrite@atom{%
    \string\codep@sbl@tag
    {\codep@currentatom}{#1}{#2}}%
}
```

Usage: `\codeptag{uid}{cat:category}` inside a definition
emits one `\codep@sbl@tag` record with the current atom's
display number.  **It has no visible typesetting effect.**
It is a pure sidecar channel for semantic metadata that
does not belong in `.aux`.  Authors who do not use the
semantic CLI can ignore `\codeptag` entirely.

### User API: `\codepnewcommand` and `\codepNewDocumentCommand`

Two new public commands replace the original `\newmath`
proposal (REVIEW_D finding #6 was the trigger; subsequent
discussion broadened scope).  They mirror LaTeX's two
canonical command-definition primitives one-for-one and
add semantic tracking on top.  Opt-in only: existing
`\newcommand` and `\NewDocumentCommand` calls are
unaffected unless you explicitly migrate them.

| Public macro | Wraps | Argument syntax mirror |
|---|---|---|
| `\codepnewcommand` | `\newcommand` | `[n]` integer arity (LaTeX 2e) |
| `\codepNewDocumentCommand` | `\NewDocumentCommand` | `{spec}` xparse arg-spec string |

**Naming convention** (per user direction 2026-04-09):
lowercase `codependent` prefix to match the existing public
API (`\codeptrack`, `\codepsuppress`, `\codeptag`),
CamelCase suffix to mirror the LaTeX kernel command being
wrapped.  Migration is a literal find-and-replace per
file: `s/\\newcommand/\\codepnewcommand/` and
`s/\\NewDocumentCommand/\\codepNewDocumentCommand/`,
with manual review for helpers you want to leave
untracked.

**No `\providecommand`, `\DeclareDocumentCommand`, or
`\renewcommand` mirrors in the first pass.**  Add later
if real use cases appear.  The two macros above cover the
common case (definitive command introduction).

#### Signature: `\codepnewcommand`

```tex
\codepnewcommand{<\cmd>}[<arity>]{<body>}
```

- `<\cmd>` is the command, **with leading backslash**
  (e.g. `\Hom`, `\Cat`).  Identical to `\newcommand`.
- `<arity>` is the optional integer argument count, in
  square brackets, default 0.  Identical to `\newcommand`.
- `<body>` is the expansion.  Uses `#1`..`#N`.  Identical
  to `\newcommand`.  Body is **not** required to be
  math-mode; any TeX content works.

The `.sty` strips the leading backslash from `<\cmd>` at
record-write time via `\@gobble\string`, so the `.sbl`
records carry the bare name.  This keeps the user-facing
syntax identical to `\newcommand` while keeping the
sidecar records readable.

#### Signature: `\codepNewDocumentCommand`

```tex
\codepNewDocumentCommand{<\cmd>}{<argspec>}{<body>}
```

- `<\cmd>` is the command with leading backslash.
- `<argspec>` is the xparse argument specification string
  (e.g. `s o m m`, `D<>{} O{default} m`, `r() m`).
  Verbatim from `\NewDocumentCommand`.
- `<body>` is the expansion.  Uses `#1`..`#N` and the
  xparse inspection macros (`\IfBooleanTF`,
  `\IfNoValueTF`, etc.).  Identical to
  `\NewDocumentCommand`.

Same backslash-stripping convention as above.

#### Examples

```tex
% \newcommand-style (math notation):
\codepnewcommand{\Hom}[2]{\mathrm{Hom}(#1,#2)}
\codepnewcommand{\id}{\mathrm{id}}

% \newcommand-style (text macro):
\codepnewcommand{\TheoremOfX}{Theorem of X}

% NewDocumentCommand-style (with optional arg):
\codepNewDocumentCommand{\Cat}{O{}}{%
  \mathsf{Cat}\IfValueT{#1}{_{#1}}%
}

% NewDocumentCommand-style (with star variant):
\codepNewDocumentCommand{\Cite}{s o m}{%
  \IfBooleanTF{#1}{[\textbf{#3}]}{[#3]}%
}
```

All four work in math mode, text mode, or both, depending
purely on what `<body>` contains.  The `.sty` does **not**
auto-`\ensuremath` the body; the user controls that.

#### Side effects at declaration time

For `\codepnewcommand`, two global (not atom-scoped)
`.sbl` records:

```tex
\codep@sbl@cmddef{Hom}{kind}{newcommand}
\codep@sbl@cmddef{Hom}{arity}{2}
\codep@sbl@cmddef{Hom}{src}{main.tex:15:1}
```

For `\codepNewDocumentCommand`, the parallel set with
`argspec` instead of `arity`:

```tex
\codep@sbl@cmddef{Cat}{kind}{NewDocumentCommand}
\codep@sbl@cmddef{Cat}{argspec}{O{}}
\codep@sbl@cmddef{Cat}{src}{main.tex:18:1}
```

The `kind` record always comes first; the CLI's parser
keys on it to decide whether to expect `arity` (integer)
or `argspec` (string).  `src` is universal.

#### Side effects at invocation time

Identical for both kinds.  The defined command is wrapped
so every invocation inside an atom emits

```tex
\codep@sbl@use{<current-atom>}{Hom}
```

via `\codep@sblwrite@atom`.  The wrapper guards on
`\ifx\codep@currentatom\@empty`: invocations OUTSIDE
any atom (section heading, caption, untracked
environment) emit **no** `\codep@sbl@use` record.
Rationale: such invocations cannot be attributed to any
atom and the CLI has no useful inference to make from
the orphaned record; the alternative of emitting a
`@global` use record was considered and rejected as
adding noise without analytic value.

#### Optionality and migration

Both macros are purely optional.  A project that does not
use the semantic CLI never needs to call them; ordinary
`\newcommand` and `\NewDocumentCommand` work fine and
produce no `.sbl` records.  The `.sty` does **not**
enforce usage of the codependent variants.

Migration from a vanilla preamble to a tracked one is
literal find-and-replace per file:

```
sed -i 's/\\newcommand/\\codepnewcommand/g' main.tex
sed -i 's/\\NewDocumentCommand/\\codepNewDocumentCommand/g' main.tex
```

with manual review for any internal helper macros you
want to leave untracked (e.g. `\newcommand{\@codep@helper}...`
inside a package).  Two-line sed script, one git commit.

For automated/batch workflows that rewrite `\newcommand`
to `\codepnewcommand` mechanically (e.g., `wrap.py` for
the arxiv test corpus), pair the rewrite with the
`conceptwarnings=off` package option to suppress the
noise from concepts that have no `\Hom*` marker.  See
Package options below.

#### Implementation sketch

The wrapped command is defined via `\NewDocumentCommand`
with an `s` (star) specifier prepended to the user's
argspec.  At call time, `\IfBooleanTF` dispatches: the
star branch emits a `\codep@sbl@def` record (and the
`\codep@concept` aux callback via §8a.9), the non-star
branch emits a `\codep@sbl@use` record (and the
`\codep@conceptref` aux callback).  Both branches
typeset the same body.  Because the star occupies `#1`
inside the wrapper, the user's own arguments are shifted
by one position: the user writes `#1..#N` in their body
but the wrapper sees them at `#2..#(N+1)`.  xparse's
`\IfBooleanTF` dispatch idiom handles this naturally —
the sketch below uses a temporary `\def` helper so the
user body can keep its natural `#1..#N` numbering.

For `\codepnewcommand`, the integer arity is translated
to a repeated-`m` argspec via `\codep@build@argspec`
(arity 0 -> empty, arity 1 -> `m`, arity 2 -> `m m`, and
so on up to 9).

```tex
% Helper: integer -> repeated xparse "m" spec.
% \codep@build@argspec{0} -> (empty)
% \codep@build@argspec{2} -> m m
\newcommand*{\codep@build@argspec}[1]{%
  \ifcase\number#1\relax
    \or m%
    \or m m%
    \or m m m%
    \or m m m m%
    \or m m m m m%
    \or m m m m m m%
    \or m m m m m m m%
    \or m m m m m m m m%
    \or m m m m m m m m m%
  \else
    \PackageError{codependent}%
      {\string\codepnewcommand\space arity \number#1\space
       out of range (max 9)}%
      {\string\newcommand\space itself is limited to arity 9;
       use \string\codepNewDocumentCommand\space for more.}%
  \fi}

% \codepnewcommand{\cmd}[arity]{body}
\NewDocumentCommand{\codepnewcommand}{m O{0} m}{%
  % #1 = \cmd (with backslash), #2 = arity, #3 = body.
  \edef\codep@tmp@name{\expandafter\@gobble\string#1}%
  % 1. Define the command via \NewDocumentCommand with a
  %    star prepended, so \Hom*  dispatches separately
  %    from \Hom.  The user's body (#3) is wrapped in a
  %    \codep@wrapcmd helper that (a) checks the star
  %    boolean at call time, (b) emits the def/use record
  %    under the currentatom guard, (c) typesets #3.
  \expandafter\codep@definewrapped
    \expandafter{\codep@tmp@name}{#1}%
    {\codep@build@argspec{#2}}{#3}%
  % 2. Emit the global declaration records (unchanged).
  \codep@sblwrite{%
    \string\codep@sbl@cmddef{\codep@tmp@name}{kind}{newcommand}}%
  \codep@sblwrite{%
    \string\codep@sbl@cmddef{\codep@tmp@name}{arity}{\number#2}}%
  \codep@sblwrite{%
    \string\codep@sbl@cmddef{\codep@tmp@name}{src}%
    {\@currfilename:\the\inputlineno:1}}%
}

% \codepNewDocumentCommand{\cmd}{argspec}{body}
\NewDocumentCommand{\codepNewDocumentCommand}{m m m}{%
  \edef\codep@tmp@name{\expandafter\@gobble\string#1}%
  % Prepend an "s" to the user's argspec.  User's #1..#N
  % inside the body become #2..#(N+1) after the shift; the
  % \codep@definewrapped helper handles the renumbering
  % via a \def indirection so the user body is written
  % against the natural numbering.
  \expandafter\codep@definewrapped
    \expandafter{\codep@tmp@name}{#1}{#2}{#3}%
  % Global declaration records (argspec is the user's raw
  % spec, NOT including the injected star).
  \codep@sblwrite{%
    \string\codep@sbl@cmddef{\codep@tmp@name}{kind}%
    {NewDocumentCommand}}%
  \codep@sblwrite{%
    \string\codep@sbl@cmddef{\codep@tmp@name}{argspec}{#2}}%
  \codep@sblwrite{%
    \string\codep@sbl@cmddef{\codep@tmp@name}{src}%
    {\@currfilename:\the\inputlineno:1}}%
}

% Shared helper: define \cmd with star-dispatch wrapper.
%   #1 = bare name (string, e.g. "Hom")
%   #2 = \cmd       (backslashed token)
%   #3 = user argspec (xparse string, possibly empty)
%   #4 = user body  (referring to #1..#N per the user's
%                    argspec, natural numbering)
\newcommand*{\codep@definewrapped}[4]{%
  % Store the user body in a helper csname so we can pass
  % the natural argument numbering through.  The helper
  % takes exactly as many arguments as the user's argspec
  % consumed positional slots.
  \expandafter\long\expandafter\def
    \csname codep@body@#1\endcsname{#4}%
  % Define the wrapped command.  xparse argspec is
  %   s <user-spec>
  % so the star lives at ##1 and the user's slots start
  % at ##2.  We dispatch on the star and, in either branch,
  % call \codep@emit@def / \codep@emit@use with the bare
  % name, then invoke the user-body helper with all of
  % ##2..##(1+N).  xparse's own \BODY forwarding would be
  % cleaner; the sketch below uses an explicit
  % \codep@forwardargs helper to make the renumbering
  % visible.
  \NewDocumentCommand{#2}{s #3}{%
    \IfBooleanTF{##1}%
      {\codep@emit@def{#1}}%
      {\codep@emit@use{#1}}%
    % Forward ##2..##(N+1) to the user body helper.  In
    % practice this is written with xparse's argument-
    % reflection primitives; see the body-helper pattern
    % used by xparse itself in ltcmd.dtx.
    \csname codep@body@#1\expandafter\endcsname
      \codep@forwardargs}%
}

% \codep@emit@def: fires on the STAR branch.
%   Records the current atom as the defining site for the
%   concept and emits both aux and .sbl records.  See §8a.9
%   for the aux-record callbacks and the pass-2 concept map.
\newcommand*{\codep@emit@def}[1]{%
  \ifx\codep@currentatom\@empty
    % No atom context (inside footnote, caption, orphan):
    % silent no-op per §8a.9 error model.  The concept will
    % later warn as "missing def site" if \cmd is used.
  \else
    % Duplicate detection: if codep@concept@<name> is
    % already defined, we have a second def-site in a
    % different atom.  Error (halts build) per §8a.9.
    \@ifundefined{codep@concept@#1}%
      {\expandafter\gdef
         \csname codep@concept@#1\endcsname
         {\codep@currentatom}%
       \if@filesw
         \immediate\write\@auxout{%
           \string\codep@concept{#1}{\codep@currentatom}}%
       \fi
       \codep@sblwrite@atom{%
         \string\codep@sbl@def{\codep@currentatom}{#1}}%
      }%
      {\PackageError{codependent}%
        {\string\\#1* defined at atoms
         \csname codep@concept@#1\endcsname\space and
         \codep@currentatom}%
        {Exactly one definition site is permitted per
         concept.  Use \string\\#1\space (without star)
         at the non-definitional site.}%
      }%
  \fi}

% \codep@emit@use: fires on the non-star branch.
%   Records a use of the concept under the current atom,
%   to be resolved to the def atom in pass 2 via §8a.9's
%   concept map.
\newcommand*{\codep@emit@use}[1]{%
  \ifx\codep@currentatom\@empty\else
    \if@filesw
      \immediate\write\@auxout{%
        \string\codep@conceptref{\codep@currentatom}{#1}}%
    \fi
    \codep@sblwrite@atom{%
      \string\codep@sbl@use{\codep@currentatom}{#1}}%
  \fi}
```

The two public macros share the star-dispatch wrapper
(`\codep@definewrapped`) and the two emit helpers
(`\codep@emit@def`, `\codep@emit@use`).  For
`\codepnewcommand`, the arity is compiled to a repeated
`m` argspec first; for `\codepNewDocumentCommand`, the
user's argspec is passed through verbatim.  In both
cases a star is prepended so every wrapped command
answers to both `\cmd` (use) and `\cmd*` (def site).

**Argument-renumbering note.**  This sketch is
deliberately not expansion-valid at every token level;
the implementer should use xparse's standard
body-helper pattern (see `ltcmd.dtx` for the reference
implementation of argument forwarding through a csname
body helper).  The key invariants are:

1. The wrapper's argspec is literally `s <user-spec>`.
2. The star boolean is `##1`.
3. The user's positional arguments are `##2..##(N+1)`.
4. The user's body is written against its natural
   `#1..#N` numbering; a def-time helper csname stores
   the body and is called with the forwarded arguments
   in natural order.

The `\codep@forwardargs` token used in the sketch is a
placeholder for xparse's actual forwarding mechanism
(`\expandafter`-chain over the numbered arguments).
Implementers familiar with xparse internals can inline
this directly.  The correctness of the dispatch does NOT
depend on how the forwarding is expressed — only that
the star is consumed at `##1` and the user's args follow.

The `\@gobble\string` trick converts `\Hom` to the bare
string `Hom` exactly once at definition time; the
captured `\codep@tmp@name` is then used in all three
record emissions and in the use-recording prelude.

The `\@currfilename` and `\inputlineno` are LaTeX kernel
primitives giving the current file and line number at
declaration time, respectively.  The column is hard-coded
to `1` because `\inputlineno` does not give column
information; a future revision might wrap the macro at a
later point in the lexer to capture columns, but this
matches the precision LaTeX itself uses for warnings.

The `\codep@sblwrite` calls (without `@atom`) bypass the
currentatom guard because `\codep@sbl@cmddef` records
are global, not atom-scoped.  See the "Guard pattern"
subsection above.

#### Why no `\providecommand` / `\DeclareDocumentCommand` mirrors?

`\providecommand` and `\DeclareDocumentCommand` differ
from their `\new*` siblings only in error-handling
behaviour (silently no-op if already defined; redefine
without error).  The semantic-tracking machinery is the
same in all four cases.  Adding `\codepProvideCommand`
and `\codepDeclareDocumentCommand` is a ~20-line
addition to the implementation and a parallel pair of
table rows in this section; it has been deferred to a
follow-up commit because real use cases haven't appeared
yet.  When they do, the pattern is mechanical.

`\renewcommand` and `\RenewDocumentCommand` are more
interesting because they imply a *re-tracking* event:
should the new definition replace the old `.sbl`
records, or append?  The clean answer is "replace the
records and leave existing `.sbl@use` records as-is
since they referred to the old definition at the time
they fired".  Defer until needed.

### Relationship to `.aux`

`.aux` and `.sbl` are siblings:

- `.aux` is LaTeX's standard sidecar.  `codependent.sty` reads
  it (for Section 8a's back-ref graph) and writes to it
  (via `\codep@atomref` and the kernel's label
  machinery).  Read-write from the `.sty` side.
- `.sbl` is codependent's sidecar.  `codependent.sty` writes it only.
  Read by the CLI (Layer 2), not by the `.sty`.
  Write-only from the `.sty` side.

`.sbl` does not duplicate anything LaTeX already writes to
`.aux`, with one deliberate exception: **labels**.  The
`.aux` has `\newlabel{key}{{num}...}` records that map
labels to display numbers, and the `.sty`'s own
`\codep@lblnum@<key>` csname already captures this.  The
`.sbl` ALSO emits `\codep@sbl@label{num}{key}` because it
lets the CLI answer "what labels does atom 1.2.4 own?"
directly from the sidecar, without joining `.aux`
`\newlabel` entries against atom boundaries.  The
redundancy is a deliberate ergonomic choice for the CLI;
it costs ~one line per label and simplifies Layer 2
considerably.

Section titles, TOC entries, page numbers, rendered
output, and anything else LaTeX already writes are NOT
reproduced in `.sbl`.

### Multi-file documents: `subfiles` / `\include` (REVIEW_E #11)

> Upstream motivation: **REVIEW_E finding #11 (MINOR,
> documentation-only).**  Users who compile subfiles
> standalone (`\documentclass[../main.tex]{subfiles}`)
> produce a per-subfile `.sbl` that does not match the
> master-compile `.sbl`.  The CLI must not confuse them.

`.sbl` is strictly per-`\jobname`, identical to how
`.aux` is per-`\jobname`.  Consequences:

- `pdflatex main.tex` produces `main.sbl` containing
  atoms from the entire project (main.tex plus all
  included subfiles), with continuous atom numbering.
- `pdflatex chapters/ch1.tex` (run standalone, using
  `\documentclass[../main.tex]{subfiles}`) produces
  `chapters/ch1.sbl` containing only ch1's atoms, with
  **local** atom numbering starting at 1.  This `.sbl`
  is correct for the standalone compile and does not
  corrupt the master's `main.sbl`.
- If both `main.sbl` and `chapters/ch1.sbl` exist on
  disk simultaneously, they describe **different
  documents** — the master version and the standalone
  draft version.  Atom numbers in `chapters/ch1.sbl`
  are not a subset of `main.sbl`'s numbering.

**CLI contract (per REVIEW_E #11 and the CLI scope
document).**  `codependent-cli analyse main.tex` reads
`main.sbl` and nothing else.  It does not discover or
merge `chapters/ch1.sbl` or any other subfile `.sbl`.
If the user wants semantic analysis, they must run
from the master document.  If they are iterating on a
single subfile for drafting purposes, the standalone
compile's local backrefs still work (via the per-subfile
`.aux` rerun) but no semantic analysis happens.

**Recommendation.**  Treat subfile standalone
compiles as drafting-only.  Run `codependent-cli` only
against the master.  This matches the normal LaTeX
workflow where `\ref{thm:A}` across subfiles is only
guaranteed to resolve in the master build.

No change is required in `codependent.sty` or
`codependent-cli` to support this; it is purely a user
documentation point.

## Package options

```latex
\usepackage{codependent}                       % all defaults
\usepackage[depth=1]{codependent}              % section.atom (default)
\usepackage[depth=2]{codependent}              % section.subsection.atom
\usepackage[equations=separate]{codependent}   % independent eq numbering (default)
\usepackage[equations=shared]{codependent}     % single counter
\usepackage[backrefs=inline]{codependent}      % "Used in" after each atom (default)
\usepackage[backrefs=appendix]{codependent}    % dependency index at end
\usepackage[backrefs=none]{codependent}        % numbering only
\usepackage[proofs=numbered]{codependent}      % proofs get atom numbers (default)
\usepackage[proofs=unnumbered]{codependent}    % proofs unnumbered
\usepackage[conceptwarnings=on]{codependent}   % warn on missing \Hom* def site (default)
\usepackage[conceptwarnings=off]{codependent}  % silent (real-world smoke test mode)
```

The `conceptwarnings` option controls whether §8a.9's
"missing def site" diagnostic for `\codepnewcommand`-defined
concepts fires as a `\PackageWarning` (default: `on`) or as
a quieter `\PackageInfo` (`off`).  The default is the correct
choice for hand-authored monographs where each tracked
command should have exactly one `\Hom*` marker.  The `off`
mode exists for batch / smoke-test workflows where
`\codepnewcommand` is generated mechanically (e.g., by
`tools/codependent/testfiles/real-world/wrap.py` rewriting
arxiv papers' `\newcommand`s) and the absence of star markers
is expected, not a defect.  The diagnostic is still emitted —
it just lands in `.log` at info level instead of warning
level, so test runners that grep for `Warning|Error` no
longer trip on it.

## Dependencies

- `etoolbox` — boolean flags, `\AtBeginEnvironment`,
  `\AtEndEnvironment`, command patching.
- `pgfkeys` — key-value option processing.
- `hyperref` (optional) — detected via `\@ifpackageloaded`.
  When present, back-ref numbers become clickable links.
  When absent, back-refs render as plain text.

No dependency on `thmtools`, `amsthm`, or `ntheorem`.
The `.sty` hooks into theorem environments by name via
`etoolbox`, regardless of which backend defines them.

## Compatibility

- **LaTeX kernel:** TeX Live 2021+ (stable `\AddToHook`,
  including `para/begin` and `para/end`).
- **Document classes:** `article`, `book`, `report`, `memoir`,
  KOMA-Script.  Auto-detects top-level sectioning command.
- **Theorem backends:** `amsthm`, `ntheorem`, or raw
  `\newtheorem`.  No preference imposed.
- **hyperref:** optional, detected at load time.

LaTeXML compatibility is a secondary goal.  The `.sty` uses
standard LaTeX2e mechanisms.  If LaTeXML needs help with
`\AddToHook` or other features, a `.latexml` binding file
can be added later without changing the package.

## File layout

```
tools/codependent/
  CONVENTIONS.md          coding conventions
  DESIGN.md               this file
  CREDITS.md              GPLv3 provenance table (dpmac port)
  codependent.sty              the package (GPLv3)
  codependent.ltxml            LaTeXML binding for HTML output (Section 8b, GPLv3)
  build.lua               l3build configuration
  testfiles/
    test-basic.lvt        basic numbering test
    test-backrefs.lvt     back-reference display test
    test-options.lvt      package option tests
    test-hyperref.lvt     hyperref integration test
    test-ntheorem.lvt     ntheorem backend test
    test-depth.lvt        depth option test
    test-equations.lvt    equations=shared test
    test-proofs.lvt       proof numbering test
    test-book.lvt         book class test
    test-nested.lvt       nested environment test
    test-starred.lvt      starred environment test
    test-latexml.lvt      LaTeXML HTML binding test (Section 8b)
  .latexindent.yaml       formatter config
```

## Non-goals

- Does not define theorem environments (user's preamble does).
- Does not define math macros.
- Does not perform semantic analysis.
- Does not generate dependency graphs.
- Does not handle UID assignment.
- Does not auto-generate labels.

## TODO

- **Margin-only numbering style.** Add `style=margin` option that
  puts ALL atom numbers (including theorems/definitions) as
  superscript margin numbers, removing the number from theorem
  headers.  Gives a visually uniform margin column.  Current
  behavior becomes `style=inline` (default for now).

- **`equations=shared` mode rework (REVIEW_E #6).**  Current
  shared-mode implementation (`\let\c@equation\c@atom`) has
  surprising interactions with `align`/`gather`/`subequations`:
  each labelled line calls `\refstepcounter{equation}`
  independently, consuming N atom numbers instead of 1.
  Future fix: alias `\c@equation` to `\c@atom` lazily,
  only at `\refstepcounter{equation}` time OUTSIDE an
  `align`/`gather`/`subequations` scope.  Inside multi-line
  environments, fall back to a private equation counter.
  Regression fixture `test-equations-shared-align.lvt`
  pins the current known-broken behaviour so the rework
  can be validated against it.

- **`\newtcolorbox` auto-registration (REVIEW_E #13).**
  Parallel to `\newlist` wrapping in Section 8a.6.k,
  wrap `\newtcolorbox` (and `\newtcolorbox[...]{name}{...}`
  with-options form) to auto-call `\codep@suppressenv`
  on the created environment.  Requires inspection of
  tcolorbox's `\newtcolorbox` signature (complex; may
  take an `xparse`-style optional-argument probe).

- **Verbatim-environment auto-suppression (REVIEW_E #14).**
  listings, minted, fancyvrb users currently have to
  manually `\codepsuppress{lstlisting}` etc.  A future
  convenience would auto-suppress common verbatim
  environment names when the respective package is
  loaded.  Out of scope for v0.1; documented in
  "Recommended preamble snippets" above.

- **`\codep@recordmanualref{label}` helper.**  For
  authors who use `\hyperref[label]{text}` and want
  codependent to still track the edge, provide an explicit
  opt-in helper command.  Currently
  `\hyperref[label]{text}` is deliberately uncovered
  (REVIEW_E #16); this helper lets the author opt back
  in on a per-site basis.

- **biblatex ordering rule** — add
  `\DeclareHookRule{begindocument/before}{codependent/backref/install}{after}{biblatex}`
  conditionally if a biblatex interaction bug surfaces
  (REVIEW_E #8).  Currently unnecessary; kept on the
  radar for forward-compat.

- **memoir-class regression testing.**  REVIEW_E #5
  flagged memoir as a BLOCKER candidate (same root
  cause as KOMA), but the fix via `cmd/<level>/before`
  hooks should cover it.  Verify with
  `test-memoir.lvt` fixture once memoir is installed
  in the test environment.

## Credit

**The back-reference machinery (Section 8a) is a direct
port of Dmitri Pavlov's `dpmac.tex`** (Plain TeX, GNU
GPLv3, 2007-2023).  The ported elements include the
defer-queue pattern, the `\recordbackref` / `\processbackref`
control flow, the per-target csname table for the inverted
adjacency list, and the self-ref dedup logic.  LaTeX-
specific adaptations (the `.aux` rerun as persistence layer,
the `\@setref` patch, the `\AddToHook` wiring) are new.

The whole of `codependent.sty` is therefore distributed under
**GNU GPL version 3** as a derivative work.  See
`tools/codependent/CREDITS.md` for the provenance table,
bucket-by-bucket attribution, and the intent to reach out
to Pavlov regarding a possible LPPL dual-license courtesy.

The shared counter, paragraph-as-atom, and "Used in"
back-reference *concepts* also originate from Pavlov's
system.
