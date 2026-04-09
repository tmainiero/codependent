# semtex.sty Design

LaTeX package for Pavlov-style automatic atom numbering and
back-reference display.  Inspired by Dmitri Pavlov's
[dpmac](https://dmitripavlov.org/tex/dpmac.tex) (Plain TeX,
GNU GPLv3, 2007-2023), adapted to LaTeX with external
back-reference computation via a generic CLI tool.

## Separation of concerns

The semtex ecosystem has three layers.  The `.sty` is the
bottom layer — it knows nothing about the layers above.

| Layer | What | Audience |
|---|---|---|
| **semtex.sty** | Atom numbering + back-ref display | Anyone (CTAN) |
| **semtex CLI** | `.aux` → `.sbr` (back-refs from `\label`/`\ref`) | Anyone using the `.sty` |
| **Project extension** | UIDs, symbol tracking, type-aware deps | Project-specific |

The `.sty` is fully standalone.  It numbers atoms with zero
external tools.  The CLI optionally generates a `.sbr` file
to enable back-reference display.  Project-specific extensions
(UIDs, `\newmath` tracking, etc.) live outside this package
entirely.

## Architecture

```
pdflatex main.tex          pass 1: .sty numbers atoms, writes .aux
semtex backrefs main.aux   reads .aux, computes back-refs, writes main.sbr
pdflatex main.tex          pass 2: .sty reads main.sbr, appends "Used in"
```

The `.sty` handles both passes.  On pass 1, `\IfFileExists`
finds no `.sbr` file and back-refs are silently omitted.
On pass 2, the file exists and back-refs render.  A single-pass
build produces a correctly numbered document — just without
back-references.

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
\usepackage{semtex}          % after all \newtheorem
\semtextrack{definition,theorem,proposition,...}
```

semtex.sty loads AFTER the theorem backend and AFTER all
`\newtheorem` declarations.  `\semtextrack{...}` performs
post-hoc aliasing of the shared theorem counter to the `atom`
counter.  It also auto-registers starred variants (e.g.,
`definition` → both `definition` and `definition*`, which
`amsthm` creates automatically).

## Numbering

### Shared counter

One counter (`atom`) for all block types: paragraphs,
definitions, theorems, propositions, lemmas, corollaries,
remarks, examples, proofs.

When `\semtextrack` is called, it:

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
\usepackage[depth=1]{semtex}  % 2.3      (default)
\usepackage[depth=2]{semtex}  % 2.1.3
\usepackage[depth=3]{semtex}  % 2.1.3.4  (if you must)
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

By default, equation numbering is independent of atom
numbering.  Atoms render as superscript margin numbers;
equations render as standard parenthesized numbers.

```latex
\usepackage[equations=separate]{semtex}  % independent (default)
\usepackage[equations=shared]{semtex}    % single counter for everything
```

In `shared` mode, `\let\c@equation\c@atom` — unstarred
equations consume atom numbers.  Starred equations
(`equation*`, `\[...\]`) do not advance any counter and
display no number — this is standard LaTeX behavior.
No gap in numbering; the next atom picks up naturally.

In `separate` mode, there is no ambiguity in "Used in" lists
because those only reference atom numbers, never equation
numbers.

### Paragraph numbering

Every paragraph gets a number via `\AddToHook{para/begin}`.
Rendered as a small superscript in the left margin:

```
^{1.1}  A category C consists of the following data...

^{1.2}  subject to the following axioms...
```

Small, unobtrusive, does not interrupt text flow.

#### Suppression mechanism

A depth counter `\semtex@nestlevel` controls suppression.
When `\semtex@nestlevel > 0`, the `para/begin` hook skips
numbering.  Any environment or command that should suppress
numbering increments `\semtex@nestlevel` on entry and decrements
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
- `\footnote` — increment `\semtex@nestlevel` before body,
  decrement after
- `\parbox` — same
- `\caption` — same

**User-extensible:**
```latex
\semtexsuppress{myenvironment}   % for environments
\semtexsuppresscmd{\mycommand}   % for commands
```

**Sectioning commands** (`\section`, `\subsection`, etc.)
suppress the heading paragraph itself.  The first content
paragraph after a section heading IS numbered.

### Theorem environment numbering

Hooked via `etoolbox`'s `\AtBeginEnvironment` and
`\AtEndEnvironment` for each environment name registered
with `\semtextrack{...}`.  No dependency on `thmtools` —
works with plain `amsthm`, `ntheorem`, or raw `\newtheorem`.

When a tracked environment opens:

1. Set `\semtex@nestlevel > 0` so paragraphs within the
   environment don't get separate numbers.
2. Adjust the displayed number to use the atom format.

The counter is NOT advanced by the hook — `\newtheorem`
already advances the aliased `atom` counter on entry.
No double-increment.

When it closes, decrement `\semtex@nestlevel`.

Result: "Definition 2.3." uses the same counter as
paragraph 2.2 before it.  Multiple paragraphs within a
single definition share one number.

**Nested tracked environments:** if `\semtex@nestlevel > 0`
when a tracked environment opens (i.e., it's inside another
tracked environment), the counter is NOT advanced.  The inner
environment is part of the outer atom.  Example: a
`definition` containing an `example` gets one atom number.

**Starred environments:** `\semtextrack{definition}` auto-
registers both `definition` and `definition*`.  Both get atom
numbers.

### Proof environments

`proof` (from `amsthm`) is not a `\newtheorem` environment.
It is hooked separately via `\AtBeginEnvironment{proof}`.

By default, proofs get their own atom number (Pavlov style).
The number renders as a superscript margin number (like
paragraphs); the "Proof." heading from `amsthm` stays as-is.

```latex
\usepackage[proofs=numbered]{semtex}    % default
\usepackage[proofs=unnumbered]{semtex}  % skip numbering
```

### Labels

No auto-generated labels.  Authors use explicit `\label{...}`
as usual.  The `.sty` does not create labels because
display-number-based labels would be unstable under
reorganization.

## Back-references

### Data file format

The generic semtex CLI reads the `.aux` file, computes
back-references from `\label`/`\ref` cross-references, and
writes `main.sbr` (`.sbr` = semtex back-refs, following the
`.aux`, `.bbl`, `.toc`, `.idx` naming tradition):

```tex
%% Generated by semtex -- do not edit
\semtex@section{1}{Categories}
\semtex@backref{1.2}{Category}{2.1, 3.4, 5.2}
\semtex@backref{1.3}{Hom-set}{2.1}
\semtex@section{2}{Functors}
\semtex@backref{2.1}{Functor}{3.1, 3.2}
```

Format: `\semtex@backref{atom-number}{atom-name}{ref-list}`.
The atom name is used in appendix mode.  Section entries
provide grouping structure for the appendix.

### Staleness detection

Pass 1: the `.sty` writes a `\semtex@auxversion{<hash>}`
entry into the `.aux` file (like `\newlabel`).

Pass 2: the `.sty` reads back the stored hash from `.aux`
data (loaded by LaTeX at `\begin{document}` before `.aux` is
truncated for rewriting) and compares it with the hash in the
`.sbr` header.  Mismatch triggers:

```
Package semtex Warning: .sbr is stale, rerun semtex backrefs
```

This follows the standard LaTeX "rerun" pattern used by
hyperref, cleveref, and others.

### Back-reference emission

Following Pavlov's approach in dpmac: back-references are
emitted at the **end of the current atom**, not the start of
the next one.

The mechanism uses `\AddToHook{para/end}` (the official
LaTeX kernel hook for paragraph completion, counterpart to
`para/begin`).  When an atom is created:

1. Look up the atom's display number in the `.sbr` data.
2. If back-refs exist, queue them into a token register
   (`\semtex@pendingbr`).
3. The `para/end` hook flushes `\semtex@pendingbr` —
   appending "Used in X, Y." at the end of the paragraph.
4. Clear the register.

For theorem environments: `\AtEndEnvironment` flushes the
pending back-ref before the environment closes.

This is the same pattern as Pavlov's `\atendbr` token
register flushed by `\finishpar` — adapted from Plain TeX
`\par` patching to the official LaTeX hook API.

No edge case with the last atom: every paragraph ends with
`\par`, which triggers the `para/end` hook.

### Inline mode (default)

At the end of each atom, if back-ref data exists, appends:

```
                            Used in 2.1, 3.4, 5.2.
```

Rendered in `\small\sffamily`.  Each number is a hyperlink
when `hyperref` is loaded.

### Appendix mode

Back-refs are collected and typeset as a structured appendix,
grouped by section.  Section titles and atom names come from
the `.sbr` file.  Continuation lines are indented past the
leader dots so long lists wrap unambiguously:

```
Dependency Index

1  Categories
   1.2  Category .............. 2.1, 2.3, 3.1, 3.4, 4.2,
                                5.1, 5.3, 7.2
   1.3  Hom-set ............... 2.1, 4.1

2  Functors
   2.1  Functor ............... 3.1, 3.2, 4.1, 4.2, 4.3,
                                5.1, 5.2, 5.3, 6.1, 6.2
```

### None mode

Numbering only, no back-references displayed.

## Package options

```latex
\usepackage{semtex}                       % all defaults
\usepackage[depth=1]{semtex}              % section.atom (default)
\usepackage[depth=2]{semtex}              % section.subsection.atom
\usepackage[equations=separate]{semtex}   % independent eq numbering (default)
\usepackage[equations=shared]{semtex}     % single counter
\usepackage[backrefs=inline]{semtex}      % "Used in" after each atom (default)
\usepackage[backrefs=appendix]{semtex}    % dependency index at end
\usepackage[backrefs=none]{semtex}        % numbering only
\usepackage[proofs=numbered]{semtex}      % proofs get atom numbers (default)
\usepackage[proofs=unnumbered]{semtex}    % proofs unnumbered
```

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
tools/semtex-sty/
  CONVENTIONS.md          coding conventions
  DESIGN.md               this file
  semtex.sty              the package
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
  .latexindent.yaml       formatter config
```

## Non-goals

- Does not define theorem environments (user's preamble does).
- Does not define math macros.
- Does not perform semantic analysis.
- Does not generate dependency graphs.
- Does not handle UID assignment.
- Does not auto-generate labels.

## Credit

Inspired by Dmitri Pavlov's dpmac (Plain TeX, GNU GPLv3,
2007-2023).  The shared counter, paragraph-as-atom, and
"Used in" back-reference concepts originate from his system.
